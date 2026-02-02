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

    # fallback: non riconosciuto
    raise ValueError(
        f"QC rule '{rname}' returned an unsupported result type: {type(res)}. "
        "Expected mask, (mask, reason), dict, or object with passed_mask/mask."
    )


# ============================================================
# QC runner
# ============================================================
def run_qc(
    df: pd.DataFrame,
    selected_rules: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, pd.DataFrame, QCStats]:
    ensure_loaded()
    rules = get_rules(selected_rules)

    print("[DEBUG] QC rules loaded:", [_rule_name(r) for r in rules])

    total = len(df)

    # snapshot metadata
    meta_snapshot: Dict[str, Optional[str]] = {
        "symbol": _first_non_blank_value(df["symbol"]) if "symbol" in df.columns else None,
        "isin": _first_non_blank_value(df["isin"]) if "isin" in df.columns else None,
    }

    keep_mask = pd.Series(True, index=df.index)
    reasons = pd.Series("", index=df.index)
    per_rule: Dict[str, int] = {}

    for rule in rules:
        rname = _rule_name(rule)
        rule_mask, rule_reason = _invoke_rule(rule, df)

        # allinea index e tipo
        rule_keep = rule_mask.reindex(df.index, fill_value=False).astype(bool)

        newly_rejected = (keep_mask & ~rule_keep).sum()
        per_rule[rname] = int(newly_rejected)

        to_mark = keep_mask & ~rule_keep
        if to_mark.any():
            reasons.loc[to_mark] = reasons.loc[to_mark].apply(
                lambda s: rule_reason if s == "" else f"{s} | {rule_reason}"
            )

        keep_mask = keep_mask & rule_keep

    cleaned = df.loc[keep_mask].copy()
    rejected = df.loc[~keep_mask].copy()
    rejected["QC_REASON"] = reasons.loc[~keep_mask].values

    # ripristina metadata se vuota
    cleaned = _ensure_metadata(cleaned, meta_snapshot)
    rejected = _ensure_metadata(rejected, meta_snapshot)

    kept = int(keep_mask.sum())
    rej = total - kept
    pct = (rej / total * 100.0) if total else 0.0

    stats = QCStats(total, kept, rej, pct, per_rule)
    return cleaned, rejected, stats
