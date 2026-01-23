from __future__ import annotations
import pandas as pd
from .base import RuleResult
from .registry import register


@register
class RuleOHLCBasic:
    name = "ohlc_basic"

    def run(self, df: pd.DataFrame) -> RuleResult:
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                passed = pd.Series([False] * len(df), index=df.index)
                return RuleResult(passed, f"Colonna mancante: {col}")

        o, h, l, c = df["open"], df["high"], df["low"], df["close"]
        passed = (h >= l) & (h >= o) & (h >= c) & (l <= o) & (l <= c)
        return RuleResult(passed_mask=passed.fillna(False), reason="OHLC incoerente (high/low vs open/close)")
