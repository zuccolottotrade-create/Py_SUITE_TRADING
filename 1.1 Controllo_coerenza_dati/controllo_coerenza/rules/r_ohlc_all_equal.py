from __future__ import annotations

import pandas as pd

from .base import RuleResult
from .registry import register


@register
class OhlcAllEqualRule:
    """
    Scarta la riga se Open == High == Low == Close.
    Barra piatta / non informativa.
    """
    name = "ohlc_all_equal"

    def run(self, df: pd.DataFrame) -> RuleResult:
        # Normalizza nomi colonna (case-insensitive)
        col_map = {str(c).strip().lower(): c for c in df.columns}
        required = ["open", "high", "low", "close"]

        missing = [c for c in required if c not in col_map]
        if missing:
            # Se mancano colonne OHLC, NON scartiamo qui (regola separata)
            passed = pd.Series(True, index=df.index)
            return RuleResult(
                passed_mask=passed,
                reason=f"missing OHLC columns (skipped)"
            )

        o = pd.to_numeric(df[col_map["open"]], errors="coerce")
        h = pd.to_numeric(df[col_map["high"]], errors="coerce")
        l = pd.to_numeric(df[col_map["low"]], errors="coerce")
        c = pd.to_numeric(df[col_map["close"]], errors="coerce")

        # True = keep row
        passed = ~(
            o.notna() & h.notna() & l.notna() & c.notna() &
            (o == h) & (h == l) & (l == c)
        )

        return RuleResult(
            passed_mask=passed,
            reason="open == high == low == close"
        )
