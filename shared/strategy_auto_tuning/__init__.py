"""
Public API minima per shared.strategy_auto_tuning
"""

from .evaluator import StrategyEvaluator, EvalResult, EvalMetrics


__all__ = [
    "StrategyEvaluator",
    "EvalResult",
    "EvalMetrics",
]


def run_selftest() -> None:
    """
    Selftest V1 (Random Search):
    - cheap checks always on
    - optional heavy run_strategia execution if SAT_SELFTEST_RUN=1
    """
    import os
    from pathlib import Path
    import tempfile

    # 1) Evaluator import + run_strategia discovery
    ev = StrategyEvaluator()
    assert ev.run_script.exists(), f"run_strategia.py not found: {ev.run_script}"
    assert ev.run_script.name == "run_strategia.py", f"unexpected run script: {ev.run_script}"

    # 2) Space build from a real config_strategy.xlsx (optional)
    # Prefer env var so selftest is stable across machines.
    cfg = os.environ.get("SAT_SELFTEST_CONFIG")
    if cfg:
        from .space import build_space_from_tuning
        space = build_space_from_tuning(Path(cfg))
        assert len(space.params) > 0, "empty TUNING space"

        # 3) Mutator: write one trial xlsx (no run_strategia)
        from .samplers import RandomSearchSampler
        from .mutator import write_trial_config

        sampler = RandomSearchSampler(seed=42)
        sample = next(sampler.iter_trials(space, 1))

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            trial_xlsx = td / "trial_selftest.xlsx"
            write_trial_config(
                base_config_path=Path(cfg),
                out_config_path=trial_xlsx,
                params=sample.params,
            )
            assert trial_xlsx.exists() and trial_xlsx.stat().st_size > 0, "trial xlsx not written"

    # 4) Optional heavy: run one evaluation if requested
    if os.environ.get("SAT_SELFTEST_RUN") == "1":
        kpi = os.environ.get("SAT_SELFTEST_INPUT")
        tf = os.environ.get("SAT_SELFTEST_TIMEFRAME", "1h")
        cfg2 = cfg or os.environ.get("SAT_SELFTEST_CONFIG")
        assert kpi and cfg2, "Set SAT_SELFTEST_INPUT and SAT_SELFTEST_CONFIG for heavy selftest"

        res = ev.evaluate(
            input_csv=Path(kpi),
            config_strategy=Path(cfg2),
            timeframe=tf,
            outdir=None,
            timeout_sec=int(os.environ.get("SAT_SELFTEST_TIMEOUT", "300")),
        )
        assert res.ok, f"evaluation failed: {res.error}"
        assert res.metrics.buy_hold_profit is not None, "missing Buy&Hold profit"
        assert res.metrics.profit is not None, "missing strategy profit"