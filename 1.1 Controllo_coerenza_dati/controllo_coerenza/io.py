from __future__ import annotations
from pathlib import Path
import pandas as pd
from pathlib import Path


DEFAULT_NUM_COLS = ("open", "high", "low", "close", "volume")


def _to_float_eu(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.replace({"": None, "None": None, "nan": None})
    # Gestione virgola come decimale
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def load_csv(path: Path, sep: str = ";") -> pd.DataFrame:
    df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False)
    # normalizza nomi colonne (opzionale): lower + strip
    df.columns = [c.strip() for c in df.columns]

    for col in DEFAULT_NUM_COLS:
        if col in df.columns:
            df[col] = _to_float_eu(df[col])

    return df



def _format_eu_number(x) -> str:
    """
    Converte un valore numerico in stringa EU:
    - decimale = ','
    - nessun separatore migliaia
    """
    if pd.isna(x):
        return ""
    try:
        # evita scientific notation, mantiene precisione originale
        s = f"{float(x):.10f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    except Exception:
        return str(x)


def export_csv(df: pd.DataFrame, path: Path, sep: str = ";") -> None:
    out = df.copy()

    # Identifica colonne numeriche REALI
    num_cols = out.select_dtypes(include=["number"]).columns

    for c in num_cols:
        out[c] = out[c].apply(_format_eu_number)

    out.to_csv(path, sep=sep, index=False)
