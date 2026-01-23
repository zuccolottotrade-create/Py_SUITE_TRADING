from __future__ import annotations
import pandas as pd
from .base import RuleResult
from .registry import register


@register
class RulePriceSanity:
    name = "price_sanity"

    def run(self, df: pd.DataFrame) -> RuleResult:
        cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]
        if not cols:
            passed = pd.Series([False] * len(df), index=df.index)
            return RuleResult(passed, "Colonne prezzo mancanti (open/high/low/close)")

        x = df[cols]
        passed = (x > 0).all(axis=1) & (x < 1_000_000).all(axis=1)
        return RuleResult(passed_mask=passed.fillna(False), reason="Prezzo non plausibile (<=0 o troppo grande)")
