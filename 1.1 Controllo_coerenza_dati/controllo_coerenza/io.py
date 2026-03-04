from __future__ import annotations

from pathlib import Path
import csv
import re

import numpy as np
import pandas as pd
import itertools


DEFAULT_NUM_COLS = ("open", "high", "low", "close", "volume")


# ============================================================
# READ: robusto (delimiter sniff + dtype=str)
# ============================================================
def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except Exception:
        return ";"


def read_any_csv(path: Path, max_sample_bytes: int = 64_000) -> pd.DataFrame:
    """
    Lettura CSV robusta:
    1) sniff delimiter
    2) rileva header reale (linea che contiene open/high/low/close)
    3) skip eventuali righe iniziali non dati (es. label strumento)
    4) fallback header=None se necessario (mapping per numero campi)
    """
    raw = path.read_bytes()
    sample = raw[:max_sample_bytes].decode("utf-8", errors="ignore")
    sep = _detect_delimiter(sample)

    lines = sample.splitlines()

    # ------------------------------------------------------------
    # 1) Rilevazione header reale (prime righe)
    # ------------------------------------------------------------
    header_row = None
    known_cols = ("open", "high", "low", "close")

    for i, line in enumerate(lines[:50]):
        lower = line.lower()
        if all(k in lower for k in known_cols):
            header_row = i
            break

    # ------------------------------------------------------------
    # 2) Lettura con header (skippando eventuale “spazzatura” iniziale)
    # ------------------------------------------------------------
    df = pd.read_csv(
        path,
        sep=sep,
        dtype=str,
        encoding="utf-8",
        engine="python",
        skiprows=header_row if header_row is not None else 0,
    )

    # se il file è vuoto o con 0 colonne, ritorna subito
    if df.shape[1] == 0:
        return df

    # ------------------------------------------------------------
    # 3) Fallback: se non vedo colonne OHLC, provo header=None e mapping
    # ------------------------------------------------------------
    cols_lower = {str(c).strip().lower() for c in df.columns}
    if not any(c in cols_lower for c in known_cols):
        df2 = pd.read_csv(
            path,
            sep=sep,
            dtype=str,
            encoding="utf-8",
            engine="python",
            header=None,
        )

        n = df2.shape[1]
        if n >= 6:
            base = ["date", "time", "open", "high", "low", "close"]
            extra = []
            if n >= 7:
                extra.append("volume")

            while len(base) + len(extra) < n:
                extra.append(f"col{len(base) + len(extra) + 1}")

            df2.columns = base + extra[: (n - len(base))]
            return df2

        return df2

    return df


# ============================================================
# NORMALIZE: schema canonico + datetime + float OHLCV
# ============================================================
def _to_float_mixed_decimal(series: pd.Series) -> pd.Series:
    """
    Converte numeri che arrivano come stringhe con virgola o punto.
    - "28,885" -> 28.885
    - "8158.0" -> 8158.0
    """
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("float64")

    s = series.astype(str).str.strip()
    s = s.replace({"": np.nan, "None": np.nan, "nan": np.nan})
    s = s.str.replace(",", ".", regex=False)  # EU -> dot
    return pd.to_numeric(s, errors="coerce").astype("float64")


def normalize_input(df: pd.DataFrame, source_path: Path | None = None) -> pd.DataFrame:
    """
    Supporta:
    - tracciato standard: symbol isin date time open high low close volume datetime
    - tracciato alternativo: Data Time Open High Low Close Volume
    Output canonico:
    - symbol, isin (opzionali)
    - datetime (Timestamp)
    - open/high/low/close/volume (float)
    """
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    # sinonimi colonne
    rename_map = {
        "data": "date",
        "giorno": "date",
        "ora": "time",
        "apertura": "open",
        "massimo": "high",
        "max": "high",
        "minimo": "low",
        "min": "low",
        "chiusura": "close",
        "volumi": "volume",
        "vol": "volume",
        # metadata / identificativi strumento
        "ticker": "symbol",
        "ric": "symbol",
        "strumento": "symbol",
        "instrument": "symbol",
        "isin_code": "isin",
    }
    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})

    # datetime: priorità a colonna esistente
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(
            df["datetime"].astype(str).str.strip(),
            errors="coerce",
            dayfirst=True,
        )
    else:
        df["datetime"] = pd.NaT

    # fallback: date + time
    if df["datetime"].isna().all():
        if "date" in df.columns and "time" in df.columns:
            dt_str = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
            df["datetime"] = pd.to_datetime(dt_str, errors="coerce", dayfirst=True)
        elif "date" in df.columns:
            df["datetime"] = pd.to_datetime(df["date"].astype(str).str.strip(), errors="coerce", dayfirst=True)

    # OHLCV float (garantisce presenza colonne)
    for col in DEFAULT_NUM_COLS:
        if col in df.columns:
            df[col] = _to_float_mixed_decimal(df[col])
        else:
            df[col] = np.nan

    # ------------------------------------------------------------
    # AUTO-DETECT OHLC ORDER (fix per feed con ordine colonne non standard)
    # Se la coerenza OHLC è molto bassa, proviamo permutazioni per riallineare.
    # ------------------------------------------------------------
    def _ohlc_pass_rate(o_: pd.Series, h_: pd.Series, l_: pd.Series, c_: pd.Series) -> float:
        m = (h_ >= l_) & (h_ >= o_) & (h_ >= c_) & (l_ <= o_) & (l_ <= c_)
        m = m.fillna(False)
        if len(m) == 0:
            return 0.0
        return float(m.mean())

    # Consideriamo solo se abbiamo abbastanza dati numerici
    if all(col in df.columns for col in ("open", "high", "low", "close")):
        o0, h0, l0, c0 = df["open"], df["high"], df["low"], df["close"]

        # sample per velocità e robustezza
        sample_n = min(len(df), 2000)
        o_s = o0.iloc[:sample_n]
        h_s = h0.iloc[:sample_n]
        l_s = l0.iloc[:sample_n]
        c_s = c0.iloc[:sample_n]

        base_rate = _ohlc_pass_rate(o_s, h_s, l_s, c_s)

        # Se passa già bene, non tocchiamo nulla
        # Soglia 0.60: se meno del 60% è coerente, probabile ordine sbagliato
        if base_rate < 0.60:
            cols = ["open", "high", "low", "close"]

            best_rate = base_rate
            best_perm = tuple(cols)

            # prova tutte le permutazioni delle 4 colonne
            for perm in itertools.permutations(cols, 4):
                oo = df[perm[0]].iloc[:sample_n]
                hh = df[perm[1]].iloc[:sample_n]
                ll = df[perm[2]].iloc[:sample_n]
                cc = df[perm[3]].iloc[:sample_n]
                r = _ohlc_pass_rate(oo, hh, ll, cc)
                if r > best_rate:
                    best_rate = r
                    best_perm = perm

            # Applichiamo solo se il miglioramento è significativo
            # e il best_rate diventa “sano”
            if best_perm != tuple(cols) and (best_rate - base_rate) >= 0.20 and best_rate >= 0.80:
                # rimappa colonne in modo coerente: open/high/low/close
                df["open"] = df[best_perm[0]]
                df["high"] = df[best_perm[1]]
                df["low"] = df[best_perm[2]]
                df["close"] = df[best_perm[3]]

                # nota diagnostica (utile nel REJECTED)
                df["PARSE_OHLC_ORDER"] = f"{best_perm} (rate {best_rate:.3f} from {base_rate:.3f})"
            else:
                df["PARSE_OHLC_ORDER"] = f"default (rate {base_rate:.3f})"
        else:
            df["PARSE_OHLC_ORDER"] = f"default (rate {base_rate:.3f})"


    # opzionali: symbol/isin
    for c in ("symbol", "isin"):
        if c not in df.columns:
            df[c] = pd.NA

    # ------------------------------------------------------------
    # FILL METADATA: se symbol/isin mancanti o vuoti, prova a inferire dal nome file
    # ------------------------------------------------------------
    def _series_blank(s: pd.Series) -> bool:
        tmp = s.astype(str).str.strip()
        tmp = tmp.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NA": pd.NA})
        return tmp.isna().all()

    if source_path is not None:
        stem = source_path.stem

        # ISIN nel nome file: 12 char alfanumerici con 2 lettere iniziali (IE00..., US..., ecc.)
        if "isin" in df.columns and _series_blank(df["isin"]):
            m_isin = re.search(r"\b([A-Z]{2}[A-Z0-9]{10})\b", stem.upper())
            if m_isin:
                df["isin"] = m_isin.group(1)

        # Symbol: token tipo FDAX15M -> FDAX
        if "symbol" in df.columns and _series_blank(df["symbol"]):
            tokens = re.split(r"[^A-Za-z0-9]+", stem)
            sym = None
            for t in tokens:
                if not t:
                    continue
                tt = t.upper()
                m_tf = re.match(r"^([A-Z]{2,15})(\d{1,4})([MHDW])$", tt)
                if m_tf:
                    sym = m_tf.group(1)
                    break

            # fallback: primo token alfabetico “ragionevole”
            if sym is None:
                for t in tokens:
                    tt = t.upper()
                    if tt.isalpha() and 2 <= len(tt) <= 15:
                        sym = tt
                        break

            if sym:
                df["symbol"] = sym

    # ordering (comodo per debug/export)
    preferred = ["symbol", "isin", "datetime", "open", "high", "low", "close", "volume"]
    rest = [c for c in df.columns if c not in preferred]
    return df[preferred + rest]


def load_csv(path: Path) -> pd.DataFrame:
    """
    Unica procedura robusta:
    read_any_csv -> normalize_input
    """
    raw = read_any_csv(path)
    return normalize_input(raw, source_path=path)


# ============================================================
# EXPORT: EU decimal comma (virgola)
# ============================================================
def _format_eu_number(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    try:
        # preserva interi
        xf = float(x)
        if np.isfinite(xf) and abs(xf - int(xf)) < 1e-12:
            return f"{int(xf)}"
        # float con virgola
        s = f"{xf:.6f}"
        return s.replace(".", ",")
    except Exception:
        return str(x)


def export_csv(df: pd.DataFrame, path: Path, sep: str = ";") -> None:
    out = df.copy()

    # format datetime per Excel
    if "datetime" in out.columns and pd.api.types.is_datetime64_any_dtype(out["datetime"]):
        out["datetime"] = out["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # format numeri EU (solo se numerici)
    num_cols = out.select_dtypes(include=["number"]).columns
    for c in num_cols:
        out[c] = out[c].apply(_format_eu_number)

    out.to_csv(path, sep=sep, index=False, encoding="utf-8")
