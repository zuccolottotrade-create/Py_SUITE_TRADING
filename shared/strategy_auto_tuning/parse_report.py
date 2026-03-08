"""
NOTE (V1):
Questo modulo non è usato da V1: il parsing delle metriche avviene in evaluator.py (_parse_metrics).
Tenuto per compatibilità/futuro refactor.
"""
# shared/strategy_auto_tuning/parse_report.py
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional


@dataclass(frozen=True)
class ParsedReport:
    buyhold_filo: Optional[float]
    net_profit_strategy: Optional[float]
    n_trades_closed: Optional[int]
    max_drawdown: Optional[float] = None


_FLOAT_RE = r"[-+]?\d[\d\s.,]*"


def _to_float_maybe(text: str) -> Optional[float]:
    s = text.strip().replace(" ", "")
    if not s:
        return None

    # EU/US robust
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return None


def parse_stdout(stdout: str) -> ParsedReport:
    """
    Parser CORE v0 per stdout di run_strategia.py.

    Pattern supportati (observed):
      - "Buy & Hold (FILO): 47.96"
      - "Sum Profit/Trade (finale cumulato): 6.09"
      - "Net Profit: 6.09"
      - lista "Trade 1: ..." (conteggio trades)
      - opzionale "Trades closed ...: 12"

    Nota: prendiamo l'ULTIMO match di NP/BH se stdout contiene più run.
    """
    buyhold = None
    net_profit = None
    n_trades = None

    # Buy & Hold (FILO) - last match wins
    bh_matches = re.findall(rf"Buy\s*&\s*Hold\s*\(FILO\)\s*:\s*({_FLOAT_RE})", stdout, re.IGNORECASE)
    if bh_matches:
        buyhold = _to_float_maybe(bh_matches[-1])

    # Net Profit: prefer "Net Profit:" else fallback "Sum Profit/Trade..."
    np_matches = re.findall(rf"\bNet\s*Profit\s*:\s*({_FLOAT_RE})", stdout, re.IGNORECASE)
    if np_matches:
        net_profit = _to_float_maybe(np_matches[-1])
    else:
        sp_matches = re.findall(
            rf"Sum\s*Profit/Trade(?:\s*\(finale\s*cumulato\))?\s*:\s*({_FLOAT_RE})",
            stdout,
            re.IGNORECASE,
        )
        if sp_matches:
            net_profit = _to_float_maybe(sp_matches[-1])

    # Trades closed explicit
    m = re.search(r"Trades\s*closed.*?:\s*(\d+)", stdout, re.IGNORECASE)
    if m:
        try:
            n_trades = int(m.group(1))
        except Exception:
            n_trades = None
    else:
        # fallback: count lines "Trade N:"
        trade_lines = re.findall(r"^Trade\s+\d+\s*:", stdout, re.MULTILINE)
        if trade_lines:
            n_trades = len(trade_lines)

    return ParsedReport(
        buyhold_filo=buyhold,
        net_profit_strategy=net_profit,
        n_trades_closed=n_trades,
        max_drawdown=None,
    )


__all__ = ["ParsedReport", "parse_stdout"]
