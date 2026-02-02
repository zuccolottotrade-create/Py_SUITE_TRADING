from __future__ import annotations

from pathlib import Path
import csv
import re

import numpy as np
import pandas as pd


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
    2) read con header
    3) se header non contiene colonne note -> retry header=None e mappa colonne per numero campi
    """
    raw = path.read_bytes()
    sample = raw[:max_sample_bytes].decode("utf-8", errors="ignore")
    sep = _detect_delimiter(sample)

    # 1) primo tentativo: header presente
    df = pd.read_csv(
        path,
        sep=sep,
        dtype=str,
        encoding="utf-8",
        engine="python",
    )

    # se il file è vuoto o con 0 colonne, ritorna subito
    if df.shape[1] == 0:
        return df

    # Heuristica: se non vedo nessuna colonna "nota", è probabile che NON ci sia header
    known = {"date", "data", "time", "open", "high", "low", "close", "volume", "datetime", "symbol", "isin"}
    cols = {str(c).strip().lower() for c in df.columns}
    if len(cols.intersection(known)) == 0:
        # 2) retry: header=None
        df2 = pd.read_csv(
            path,
            sep=sep,
            dtype=str,
            encoding="utf-8",
            engine="python",
            header=None,
        )
        # mappa colonne in base a numero campi (minimo atteso 6: date time open high low close)
        n = df2.shape[1]
        if n >= 6:
            base = ["date", "time", "open", "high", "low", "close"]
            extra = []
            if n >= 7:
                extra.append("volume")
            # se ci sono ancora colonne, le chiamo colN
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
