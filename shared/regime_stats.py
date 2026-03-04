#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import itertools
import numpy as np
import pandas as pd
from scipy.stats import kruskal, mannwhitneyu

# -----------------------------
# CONFIG
# -----------------------------
CSV_PATH = Path("/Users/claudio 1/Py_SUITE_TRADING/_data/Test Data/KPI_CLEAN_RAW_EQQQ_NA_30min_20260209_135205.csv")
SEP = ";"
REGIME_COL = "REGIME_L1"
PRICE_COL = "close"
DATETIME_COL = "datetime"  # optional
H_LIST = [5, 20]           # pairwise su r5 e r20

CANONICAL = ["TREND_UP", "TREND_DOWN", "TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN"]


# -----------------------------
# Helpers
# -----------------------------
def to_float_series(x: pd.Series) -> pd.Series:
    """Robust float conversion EU/US."""
    if pd.api.types.is_numeric_dtype(x):
        return x.astype("float64")

    s = x.astype(str).str.strip()
    has_dot = s.str.contains(r"\.", regex=True, na=False)
    has_comma = s.str.contains(r",", regex=True, na=False)
    both = has_dot & has_comma
    s2 = s.copy()

    eu = both & (s.str.rfind(",") > s.str.rfind("."))
    s2.loc[eu] = s.loc[eu].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)

    us = both & ~eu
    s2.loc[us] = s.loc[us].str.replace(",", "", regex=False)

    only_comma = has_comma & ~has_dot
    s2.loc[only_comma] = s.loc[only_comma].str.replace(",", ".", regex=False)

    return pd.to_numeric(s2, errors="coerce").astype("float64")


def forward_return(s: pd.Series, h: int) -> pd.Series:
    return np.log(s.shift(-h) / s)


def fmt_eu(x: float | int | None, d: int = 6) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return f"{float(x):.{d}f}".replace(".", ",")


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cliff's Delta: effect size non parametrico.
    Intervallo [-1, +1]. 0 = nessuna differenza.
    Implementazione O(n*m) (ok per sample size tipici dei regimi).
    """
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return float("nan")

    gt = 0
    lt = 0
    # loop semplice (light). Se vuoi ottimizzare, lo facciamo dopo.
    for x in a:
        gt += np.sum(x > b)
        lt += np.sum(x < b)
    return (gt - lt) / (len(a) * len(b))


def delta_label(d: float) -> str:
    """
    Soglie tipiche (Romano et al.):
    |d| < 0.147 = negligible
    < 0.33 = small
    < 0.474 = medium
    >= 0.474 = large
    """
    if np.isnan(d):
        return ""
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


# -----------------------------
# Load
# -----------------------------
df = pd.read_csv(CSV_PATH, sep=SEP, dtype=str, keep_default_na=False)

if REGIME_COL not in df.columns:
    raise SystemExit(f"[ERR] Colonna regime mancante: {REGIME_COL}")
if PRICE_COL not in df.columns:
    raise SystemExit(f"[ERR] Colonna prezzo mancante: {PRICE_COL}")

df[PRICE_COL] = to_float_series(df[PRICE_COL])
df[REGIME_COL] = df[REGIME_COL].astype(str).str.strip().str.upper()

if DATETIME_COL in df.columns:
    dt = pd.to_datetime(df[DATETIME_COL], errors="coerce")
    df = df.assign(_dt=dt).sort_values("_dt").drop(columns=["_dt"])

# Forward returns
for h in H_LIST:
    df[f"r{h}"] = forward_return(df[PRICE_COL], h)

# common support: drop tail for max horizon
df = df.dropna(subset=[f"r{max(H_LIST)}"]).copy()

# Regimi presenti
regimes = sorted(df[REGIME_COL].dropna().unique().tolist(), key=lambda x: CANONICAL.index(x) if x in CANONICAL else 999)

# -----------------------------
# Kruskal sanity
# -----------------------------
print("\n=== KRUSKAL_SANITY ===")
for h in H_LIST:
    groups = [df.loc[df[REGIME_COL] == r, f"r{h}"].astype(float).values for r in regimes]
    p = float(kruskal(*groups).pvalue) if len(groups) >= 2 else float("nan")
    print(f"r{h} p={fmt_eu(p, 6)}")

# -----------------------------
# Pairwise Mann–Whitney + Bonferroni + Cliff's Delta
# -----------------------------
out_rows = []
for h in H_LIST:
    metric = f"r{h}"
    pairs = list(itertools.combinations(regimes, 2))
    m = len(pairs)

    for a_reg, b_reg in pairs:
        a = df.loc[df[REGIME_COL] == a_reg, metric].astype(float).values
        b = df.loc[df[REGIME_COL] == b_reg, metric].astype(float).values

        a = a[~np.isnan(a)]
        b = b[~np.isnan(b)]
        if len(a) < 20 or len(b) < 20:
            continue

        p = float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
        p_bonf = min(p * m, 1.0)

        med_a = float(np.median(a))
        med_b = float(np.median(b))
        dlt = float(cliffs_delta(a, b))

        out_rows.append({
            "metric": metric,
            "A": a_reg,
            "B": b_reg,
            "n_A": int(len(a)),
            "n_B": int(len(b)),
            "median_A": med_a,
            "median_B": med_b,
            "delta_median(A-B)": med_a - med_b,
            "p": p,
            "p_bonf": p_bonf,
            "sig_0.05_bonf": bool(p_bonf < 0.05),
            "cliffs_delta": dlt,
            "delta_size": delta_label(dlt),
        })

pairwise = pd.DataFrame(out_rows)

# Ordina: prima significativi, poi p_bonf crescente
if not pairwise.empty:
    pairwise = pairwise.sort_values(["metric", "sig_0.05_bonf", "p_bonf"], ascending=[True, False, True]).reset_index(drop=True)

print("\n=== PAIRWISE_MANNWHITNEY (Bonferroni) + CLIFFS_DELTA ===")
if pairwise.empty:
    print("Nessuna coppia con sample size sufficiente.")
else:
    show = pairwise.copy()

    # EU formatting
    for c in ["median_A", "median_B", "delta_median(A-B)", "p", "p_bonf", "cliffs_delta"]:
        show[c] = show[c].apply(lambda x: fmt_eu(x, 6))

    print(show.to_string(index=False))
