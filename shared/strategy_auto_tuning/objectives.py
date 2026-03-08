# shared/strategy_auto_tuning/objectives.py
"""
Strategy Auto-Tuning — Objectives (V1)

Score to minimize:
    alpha = NP_strat - NP_bh
    score = -alpha + penalties

Hard constraints (V1):
- n_trades_closed >= N_min  (avoid 'miracle' single trade)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .evaluator import EvalMetrics


@dataclass(frozen=True)
class ObjectiveSpec:
    n_min_trades: int = 5
    drawdown_weight: float = 0.5
    penalty_hard: float = 1e9


@dataclass(frozen=True)
class ObjectiveResult:
    alpha_vs_buyhold: Optional[float]
    score: float
    penalty: float
    ok: bool
    reason: Optional[str]


def compute_objective(metrics: EvalMetrics, spec: ObjectiveSpec) -> ObjectiveResult:
    penalty = 0.0
    reason = None

    profit = metrics.profit
    drawdown = metrics.max_drawdown
    trade_count = metrics.trade_count
    alpha_vs_buyhold = metrics.alpha_vs_buyhold

    if profit is None or drawdown is None:
        return ObjectiveResult(
            alpha_vs_buyhold=alpha_vs_buyhold,
            score=spec.penalty_hard,
            penalty=spec.penalty_hard,
            ok=False,
            reason="missing profit or max_drawdown",
        )

    if trade_count is None:
        penalty += spec.penalty_hard
        reason = "missing trade_count"
    elif int(trade_count) < int(spec.n_min_trades):
        penalty += spec.penalty_hard
        reason = f"trade_count {trade_count} < N_min {spec.n_min_trades}"

    score = float(profit) - float(spec.drawdown_weight) * float(drawdown)
    score -= penalty
    ok = penalty == 0.0

    return ObjectiveResult(
        alpha_vs_buyhold=alpha_vs_buyhold,
        score=score,
        penalty=penalty,
        ok=ok,
        reason=reason,
    )