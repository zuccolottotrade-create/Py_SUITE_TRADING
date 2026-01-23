from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd

from .rules import ensure_loaded
from .rules.registry import get_rules
from .rules.base import CoherenceRule


@dataclass
class QCStats:
    total_rows: int
    kept_rows: int
    rejected_rows: int
    rejected_pct: float
    per_rule_rejections: Dict[str, int]


def run_qc(df: pd.DataFrame, selected_rules: Optional[List[str]] = None) -> tuple[pd.DataFrame, pd.DataFrame, QCStats]:
    ensure_loaded()
    rules: List[CoherenceRule] = get_rules(selected_rules)
    print("[DEBUG] QC rules loaded:", [r.name for r in rules])

    total = len(df)
    if total == 0:
        stats = QCStats(0, 0, 0, 0.0, {})
        return df.copy(), df.copy(), stats

    keep_mask = pd.Series(True, index=df.index)
    reasons = pd.Series("", index=df.index, dtype="object")
    per_rule: Dict[str, int] = {}

    for rule in rules:
        res = rule.run(df)
        if res is None:
            raise RuntimeError(
                f"QC rule '{rule.name}' returned None. Expected RuleResult(passed_mask=..., reason=...)."
            )
        if not hasattr(res, "passed_mask"):
            raise RuntimeError(
                f"QC rule '{rule.name}' returned invalid result: {type(res)}. Expected RuleResult."
            )

        rule_keep = res.passed_mask.reindex(df.index).fillna(False)

        # Conteggio scarti per regola (sul dataset completo)
        per_rule[rule.name] = int((~rule_keep).sum())

        # Righe che vengono bocciate "per la prima volta" da questa regola
        newly_failed = keep_mask & (~rule_keep)
        if newly_failed.any():
            reasons.loc[newly_failed] = reasons.loc[newly_failed].apply(
                lambda s: res.reason if s == "" else f"{s} | {res.reason}"
            )

        keep_mask = keep_mask & rule_keep

    cleaned = df.loc[keep_mask].copy()
    rejected = df.loc[~keep_mask].copy()
    rejected["QC_REASON"] = reasons.loc[~keep_mask].values

    kept = int(keep_mask.sum())
    rej = total - kept
    pct = (rej / total * 100.0) if total else 0.0

    stats = QCStats(total, kept, rej, pct, per_rule)
    return cleaned, rejected, stats
