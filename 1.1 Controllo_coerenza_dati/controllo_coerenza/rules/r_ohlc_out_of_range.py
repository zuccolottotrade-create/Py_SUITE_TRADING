from __future__ import annotations

import pandas as pd

from .base import RuleResult
from .registry import register


@register
class OhlcOutOfRangeRule:
    """
    Scarta la riga se:
    - High < Low
    - Open o Close fuori dall'intervallo [Low, High]
    """
    name = "ohlc_out_of_range"

    def run(self, df: pd.DataFrame) -> RuleResult:
        # Normalizza nomi colonna (case-insensitive)
        col_map = {str(c).strip().lower(): c for c in df.columns}
        required = ["open", "high", "low", "close"]

        missing = [c for c in required if c not in col_map]
        if missing:
            # Se mancano colonne OHLC, NON scartiamo qui
            passed = pd.Series(True, index=df.index)
            return RuleResult(
                passed_mask=passed,
                reason="missing OHLC columns (skipped)"
            )

        o = pd.to_numeric(df[col_map["open"]], errors="coerce")
        h = pd.to_numeric(df[col_map["high"]], errors="coerce")
        l = pd.to_numeric(df[col_map["low"]], errors="coerce")
        c = pd.to_numeric(df[col_map["close"]], errors="coerce")

        # Condizioni di incoerenza
        invalid = (
            (h < l) |
            (o < l) | (o > h) |
            (c < l) | (c > h)
        )

        # True = keep row
        passed = ~invalid

        return RuleResult(
            passed_mask=passed,
            reason="OHLC out of range"
        )
