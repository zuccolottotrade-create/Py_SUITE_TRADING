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

# ============================================================
# QC RUNNER (entrypoint per CLI)
# ============================================================
def run_qc(
    df: pd.DataFrame,
    *,
    selected_rules: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, QCStats]:
    """
    Applica le regole QC al DataFrame.

    Returns:
      cleaned_df, rejected_df, stats(QCStats)
    """
    if df is None or df.empty:
        stats = QCStats(
            total_rows=0,
            kept_rows=0,
            rejected_rows=0,
            rejected_pct=0.0,
            per_rule_rejections={},
        )
        return df.copy() if df is not None else pd.DataFrame(), pd.DataFrame(), stats

    # ------------------------------------------------------------
    # Meta: preserva symbol/isin se presenti in qualche riga
    # ------------------------------------------------------------
    meta = {}
    if "symbol" in df.columns:
        meta["symbol"] = _first_non_blank_value(df["symbol"])
    else:
        meta["symbol"] = None

    if "isin" in df.columns:
        meta["isin"] = _first_non_blank_value(df["isin"])
    else:
        meta["isin"] = None

    # ------------------------------------------------------------
    # Load rules registry
    # ------------------------------------------------------------
    ensure_loaded()
    rules_map = get_rules()

    # Normalizza a dict name->rule
    if isinstance(rules_map, list):
        rules_map = {_rule_name(r): r for r in rules_map}
    elif not isinstance(rules_map, dict):
        rules_map = {}

    # Filtro opzionale per nomi regola
    if selected_rules:
        wanted = set([str(x).strip() for x in selected_rules if str(x).strip() != ""])
        rules_map = {name: rule for name, rule in rules_map.items() if name in wanted}

    total_rows = len(df)

    # Se non ci sono regole: no-op (ma stats coerenti)
    if not rules_map:
        cleaned = _ensure_metadata(df, meta)
        rejected = df.iloc[0:0].copy()  # vuoto con stesse colonne
        rejected = _ensure_metadata(rejected, meta)

        stats = QCStats(
            total_rows=total_rows,
            kept_rows=len(cleaned),
            rejected_rows=0,
            rejected_pct=0.0,
            per_rule_rejections={},
        )
        return cleaned, rejected, stats

    # ------------------------------------------------------------
    # Apply rules (AND logico): una riga è tenuta solo se passa tutte
    # ------------------------------------------------------------
    kept_mask = pd.Series(True, index=df.index)
    fail_rules = pd.Series("", index=df.index, dtype="object")  # accumulo motivi
    per_rule_rej: Dict[str, int] = {}

    for name, rule in rules_map.items():
        rule_mask, reason = _invoke_rule(rule, df)

        # Conta rifiuti "marginali" tra quelli ancora kept
        newly_rejected = kept_mask & (~rule_mask)
        per_rule_rej[name] = int(newly_rejected.sum())

        # Accumula reason sulle righe che falliscono (anche se già fallite prima)
        # (manteniamo lista separata da ';')
        fail_rules.loc[~rule_mask] = fail_rules.loc[~rule_mask].apply(
            lambda s: (s + ";" if s else "") + str(reason)
        )

        kept_mask &= rule_mask

    cleaned = df.loc[kept_mask].copy()
    rejected = df.loc[~kept_mask].copy()

    # aggiungi colonna motivi sul rejected (utile a debug)
    if not rejected.empty:
        rejected["QC_FAIL_REASON"] = fail_rules.loc[~kept_mask].values

    cleaned = _ensure_metadata(cleaned, meta)
    rejected = _ensure_metadata(rejected, meta)

    rejected_rows = int((~kept_mask).sum())
    kept_rows = int(kept_mask.sum())
    rejected_pct = (rejected_rows / total_rows * 100.0) if total_rows > 0 else 0.0

    stats = QCStats(
        total_rows=total_rows,
        kept_rows=kept_rows,
        rejected_rows=rejected_rows,
        rejected_pct=rejected_pct,
        per_rule_rejections=per_rule_rej,
    )

    return cleaned, rejected, stats
