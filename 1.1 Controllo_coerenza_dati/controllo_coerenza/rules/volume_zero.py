from __future__ import annotations

import pandas as pd

from .base import RuleResult
from .registry import register


@register
class VolumeZeroRule:
    name = "volume_zero"

    def run(self, df: pd.DataFrame) -> RuleResult:
        col_map = {str(c).strip().lower(): c for c in df.columns}

        if "volume" not in col_map:
            passed = pd.Series(True, index=df.index)
            return RuleResult(passed_mask=passed, reason="volume column not found (skipped)")

        vol_col = col_map["volume"]
        vol = pd.to_numeric(df[vol_col], errors="coerce")

        passed = (vol != 0) | (vol.isna())
        return RuleResult(passed_mask=passed, reason="volume == 0")

