from __future__ import annotations

import pandas as pd

from .base import RuleResult
from .registry import register


@register
class DuplicateTimestampRule:
    """
    Scarta le righe con timestamp duplicato.
    Priorità colonne:
    - 'datetime' se presente
    - altrimenti ('date', 'time')
    """
    name = "duplicate_timestamp"

    def run(self, df: pd.DataFrame) -> RuleResult:
        col_map = {str(c).strip().lower(): c for c in df.columns}

        # Caso 1: colonna datetime unica
        if "datetime" in col_map:
            key = df[col_map["datetime"]].astype(str).str.strip()
            dup = key.duplicated(keep="first")
            passed = ~dup
            return RuleResult(passed_mask=passed, reason="duplicate timestamp")

        # Caso 2: date + time
        if "date" in col_map and "time" in col_map:
            d = df[col_map["date"]].astype(str).str.strip()
            t = df[col_map["time"]].astype(str).str.strip()
            key = d + " " + t
            dup = key.duplicated(keep="first")
            passed = ~dup
            return RuleResult(passed_mask=passed, reason="duplicate timestamp")

        # Se non ho colonne tempo note: non scarto (stand-alone)
        passed = pd.Series(True, index=df.index)
        return RuleResult(passed_mask=passed, reason="missing datetime/date+time (skipped)")
