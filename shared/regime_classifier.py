# Py_SUITE_TRADING/shared/regime/regime_classifier.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeConfig:
    # Indicator columns
    col_adx: str = "KPI_ADX_14"
    col_atr_pct: str = "KPI_ATR_PCT_14"
    col_squeeze: Optional[str] = "KPI_SQUEEZE_ON_20"  # set None to disable

    # Percentiles (static on full dataset)
    p_adx_range: float = 0.40   # P40
    p_adx_trend: float = 0.70   # P70
    p_atr_low: float = 0.33     # P33
    p_atr_high: float = 0.67    # P67

    # Smoothing majority vote
    smooth_window: int = 12
    smooth_majority: int = 7  # >=7 on 12

    # Output columns
    out_raw: str = "REGIME_RAW"
    out_final: str = "REGIME_FINAL"
    out_code: str = "REGIME_CODE"

    # Labels
    label_range: str = "RANGE_LOW_VOL"
    label_trend: str = "TREND"
    label_mixed: str = "MIXED"


def to_float_eu(series: pd.Series) -> pd.Series:
    """Convert EU-formatted numeric strings to float.
    Examples: '1.234,56' -> 1234.56, '0,628' -> 0.628.
    """

    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)

    s = series.astype(str).str.strip()
    s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan})

    # Remove thousands separators '.' and convert decimal ',' -> '.'
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


def _quantile_safe(x: pd.Series, q: float) -> float:
    v = x.dropna().astype(float)
    if len(v) == 0:
        return float("nan")
    return float(v.quantile(q))


def compute_thresholds(df: pd.DataFrame, cfg: RegimeConfig) -> Dict[str, float]:
    adx = to_float_eu(df[cfg.col_adx]) if cfg.col_adx in df.columns else pd.Series(dtype=float)
    atrp = to_float_eu(df[cfg.col_atr_pct]) if cfg.col_atr_pct in df.columns else pd.Series(dtype=float)
    return {
        "adx_range": _quantile_safe(adx, cfg.p_adx_range),
        "adx_trend": _quantile_safe(adx, cfg.p_adx_trend),
        "atr_low": _quantile_safe(atrp, cfg.p_atr_low),
        "atr_high": _quantile_safe(atrp, cfg.p_atr_high),
    }


def classify_raw(df: pd.DataFrame, cfg: RegimeConfig, th: Dict[str, float]) -> pd.Series:
    if cfg.col_adx not in df.columns or cfg.col_atr_pct not in df.columns:
        return pd.Series([cfg.label_mixed] * len(df), index=df.index)

    adx = to_float_eu(df[cfg.col_adx])
    atrp = to_float_eu(df[cfg.col_atr_pct])

    m_range = (adx < th["adx_range"]) & (atrp < th["atr_low"])
    m_trend = (adx > th["adx_trend"]) & (atrp > th["atr_high"])

    if cfg.col_squeeze and (cfg.col_squeeze in df.columns):
        sq = to_float_eu(df[cfg.col_squeeze]).fillna(0.0)
        m_range = m_range & (sq >= 1.0)

    raw = np.where(m_range, cfg.label_range, np.where(m_trend, cfg.label_trend, cfg.label_mixed))
    return pd.Series(raw, index=df.index)


def smooth_majority_vote(regime_raw: pd.Series, cfg: RegimeConfig) -> pd.Series:
    w = int(cfg.smooth_window)
    k = int(cfg.smooth_majority)
    labels = [cfg.label_range, cfg.label_trend, cfg.label_mixed]

    arr = regime_raw.astype(str).to_numpy()
    out = np.empty(len(arr), dtype=object)

    for i in range(len(arr)):
        start = max(0, i - w + 1)
        window = arr[start : i + 1]

        best_label = cfg.label_mixed
        best_count = -1
        for lab in labels:
            c = int(np.sum(window == lab))
            if c > best_count:
                best_count = c
                best_label = lab

        out[i] = best_label if best_count >= k else cfg.label_mixed

    return pd.Series(out, index=regime_raw.index)


def add_regime_columns(df: pd.DataFrame, cfg: Optional[RegimeConfig] = None) -> Tuple[pd.DataFrame, Dict[str, float]]:
    cfg = cfg or RegimeConfig()
    th = compute_thresholds(df, cfg)
    raw = classify_raw(df, cfg, th)
    final = smooth_majority_vote(raw, cfg)

    code_map = {cfg.label_mixed: 0, cfg.label_range: 1, cfg.label_trend: 2}
    code = final.map(code_map).fillna(0).astype(int)

    out = df.copy()
    out[cfg.out_raw] = raw
    out[cfg.out_final] = final
    out[cfg.out_code] = code
    return out, th


def add_regime_columns_inplace(df: pd.DataFrame, cfg: Optional[RegimeConfig] = None) -> Dict[str, float]:
    cfg = cfg or RegimeConfig()
    th = compute_thresholds(df, cfg)
    raw = classify_raw(df, cfg, th)
    final = smooth_majority_vote(raw, cfg)

    code_map = {cfg.label_mixed: 0, cfg.label_range: 1, cfg.label_trend: 2}

    df[cfg.out_raw] = raw
    df[cfg.out_final] = final
    df[cfg.out_code] = final.map(code_map).fillna(0).astype(int)
    return th

def apply_regime(df):
    add_regime_columns_inplace(df)
    return df
