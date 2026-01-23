from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import pandas as pd


@dataclass(frozen=True)
class RuleResult:
    passed_mask: pd.Series  # True=keep row
    reason: str             # reason label when failing


class CoherenceRule(Protocol):
    name: str
    def run(self, df: pd.DataFrame) -> RuleResult: ...
