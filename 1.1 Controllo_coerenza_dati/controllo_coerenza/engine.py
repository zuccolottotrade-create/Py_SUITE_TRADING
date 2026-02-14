from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

from .rules import ensure_loaded
from .rules.registry import get_rules


@dataclass
class QCStats:
    total_rows: int
    kept_rows: int
    rejected_rows: int
    rejected_pct: float
    per_rule_rejections: Dict[str, int]


# ============================================================
# Metadata helpers (symbol/isin)
# ============================================================
def _first_non_blank_value(series: pd.Series) -> Optional[str]:
    if series is None or series.empty:
        return None
    s = series.astype(str).str.strip()
    s = s.replace(
        {
            "": pd.NA,
            "nan": pd.NA,
            "NaN": pd.NA,
            "none": pd.NA,
            "None": pd.NA,
            "NA": pd.NA,
            "na": pd.NA,
        }
    )
    s = s.dropna()
    if s.empty:
        return None
    return str(s.iloc[0]).strip()


def _series_is_all_blank(series: pd.Series) -> bool:
    return _first_non_blank_value(series) is None


def _ensure_metadata(df: pd.DataFrame, meta: Dict[str, Optional[str]]) -> pd.DataFrame:
    out = df.copy()
    for col in ("symbol", "isin"):
        if col not in out.columns:
            out[col] = pd.NA

        if _series_is_all_blank(out[col]):
            val = meta.get(col)
            if val is not None and str(val).strip() != "":
                out[col] = val
            else:
                out[col] = pd.NA
    return out


# ============================================================
# Rule invocation compatibility layer
# ============================================================
def _rule_name(rule: Any) -> str:
    return getattr(rule, "name", rule.__class__.__name__)


def _invoke_rule(rule: Any, df: pd.DataFrame) -> Tuple[pd.Series, str]:
    """
    Supporta diversi stili di regole:
      - rule.apply(df) -> RuleResult(passed_mask, reason) o simili
      - rule.run(df)   -> ...
      - rule.check(df) -> ...
      - rule(df)       -> ...
    Formati di ritorno gestiti:
      A) oggetto con attributi passed_mask + reason
      B) tuple(mask, reason)
      C) solo mask (pd.Series / array-like) -> reason = nome regola
      D) dict con chiavi 'passed_mask'/'mask' e 'reason'
    """
    # 1) chiama il metodo disponibile
    if hasattr(rule, "apply") and callable(getattr(rule, "apply")):
        res = rule.apply(df)
    elif hasattr(rule, "run") and callable(getattr(rule, "run")):
        res = rule.run(df)
    elif hasattr(rule, "check") and callable(getattr(rule, "check")):
        res = rule.check(df)
    elif callable(rule):
        res = rule(df)
    else:
        raise AttributeError(f"Rule '{_rule_name(rule)}' has no apply/run/check and is not callable.")

    rname = _rule_name(rule)

    # 2) normalizza result -> (mask, reason)
    if res is None:
        raise ValueError(f"QC rule '{rname}' returned None. Expected a mask or (mask, reason).")

    # dict
    if isinstance(res, dict):
        reason = str(res.get("reason") or rname)
        mask = res.get("passed_mask", res.get("mask", None))
        if mask is None:
            raise ValueError(f"QC rule '{rname}' returned dict without 'mask'/'passed_mask'.")
        mask = pd.Series(mask, index=df.index)
        return mask.astype(bool), reason

    # tuple/list (mask, reason)
    if isinstance(res, (tuple, list)) and len(res) == 2:
        mask, reason = res
        mask = pd.Series(mask, index=df.index)
        return mask.astype(bool), str(reason)

    # object with attributes
    if hasattr(res, "passed_mask"):
        mask = getattr(res, "passed_mask")
        reason = getattr(res, "reason", rname)
        mask = pd.Series(mask, index=df.index)
        return mask.astype(bool), str(reason)

    if hasattr(res, "mask"):
        mask = getattr(res, "mask")
        reason = getattr(res, "reason", rname)
        mask = pd.Series(mask, index=df.index)
        return mask.astype(bool), str(reason)

    # plain mask
    if isinstance(res, (pd.Series, list, tuple)):
        mask = pd.Series(res, index=df.index)
        return mask.astype(bool), rname