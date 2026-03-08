# shared/strategy_auto_tuning/cli.py
"""
Strategy Auto-Tuning — CLI (V1)

Commands:
- eval: run single evaluation (no tuning)
- autotune: Random Search V1 using TUNING sheet
- autotune-regimes: regime-wise autotune, one ENTRY group at a time
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .engine import run_autotune_v1, run_autotune_regimes_v1
from .evaluator import StrategyEvaluator


def _p(x: str) -> Path:
    return Path(x).expanduser().resolve()


def cmd_eval(args: argparse.Namespace) -> int:
    ev = StrategyEvaluator()
    res = ev.evaluate(
        input_csv=_p(args.input),
        config_strategy=_p(args.config),
        timeframe=args.timeframe,
        outdir=_p(args.outdir) if args.outdir else None,
        timeout_sec=int(args.timeout),
    )

    print("OK:", res.ok)
    if res.error:
        print("ERROR:", res.error)
    print("Returncode:", res.returncode)
    m = res.metrics
    print(f"Profit: {m.profit}")
    print(f"Profit/Trade: {m.profit_per_trade}")
    print(f"Trade Count: {m.trade_count}")
    print(f"Max Drawdown: {m.max_drawdown}")
    print(f"Alpha vs Buy&Hold: {m.alpha_vs_buyhold}")
    print(f"Buy & Hold Profit: {m.buy_hold_profit}")
    return 0 if res.ok else 3


def cmd_autotune(args: argparse.Namespace) -> int:
    outdir = run_autotune_v1(
        input_csv=_p(args.input),
        config_strategy=_p(args.config),
        timeframe=args.timeframe,
        trials=int(args.trials),
        seed=int(args.seed),
        outdir=_p(args.outdir) if args.outdir else None,
        n_min_trades=int(args.n_min_trades),
        timeout_sec=int(args.timeout),
    )

    print(f"AUTOTUNE DONE. Outdir: {outdir}")
    print(f"- trials.csv: {outdir / 'trials.csv'}")
    print(f"- best.xlsx:  {outdir / 'best.xlsx'}")
    return 0

def cmd_autotune_regimes(args: argparse.Namespace) -> int:
    if args.regimes:
        regimes = [x.strip() for x in args.regimes.split(",") if x.strip()]
    else:
        regimes = []
    print("Requested regimes:", regimes if regimes else "<auto-detect>")

    outdir = run_autotune_regimes_v1(
        input_csv=Path(args.input),
        config_strategy=Path(args.config),
        timeframe=args.timeframe,
        regimes=regimes,
        trials=args.trials,
        seed=args.seed,
        train_ratio=args.train_ratio,
        outdir=Path(args.outdir) if args.outdir else None,
        n_min_trades=args.n_min_trades,
        timeout_sec=args.timeout,
        interactive_selection=True,
    )
    print(f"AUTOTUNE-REGIMES DONE. Outdir: {outdir}")
    print(f"- per_regime dir: {outdir / 'per_regime'}")
    print(f"- selection dir:  {outdir / 'selection'}")
    print(f"- final report:   {outdir / 'final_report'}")
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="strategy_auto_tuning", add_help=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    # eval
    pe = sub.add_parser("eval", help="Run a single evaluation (no tuning)")
    pe.add_argument("--input", required=True, help="Path KPI CSV")
    pe.add_argument("--config", required=True, help="Path config_strategy.xlsx")
    pe.add_argument("--timeframe", required=True, help="Timeframe string (e.g. 30m, 1h, 1d)")
    pe.add_argument("--outdir", default=None, help="Optional output dir for run_strategia artifacts")
    pe.add_argument("--timeout", default=300, type=int, help="Timeout seconds for run_strategia")
    pe.set_defaults(func=cmd_eval)

    # autotune
    pa = sub.add_parser("autotune", help="Random Search V1 on TUNING sheet")
    pa.add_argument("--input", required=True, help="Path KPI CSV")
    pa.add_argument("--config", required=True, help="Path config_strategy.xlsx")
    pa.add_argument("--timeframe", required=True, help="Timeframe string (e.g. 30m, 1h, 1d)")
    pa.add_argument("--trials", default=50, type=int, help="Number of trials")
    pa.add_argument("--seed", default=42, type=int, help="Random seed")
    pa.add_argument("--n-min-trades", default=5, type=int, help="Hard constraint min closed trades")
    pa.add_argument("--outdir", default=None, help="Optional output dir (default: _data/strategy_tuning_runs/<ts>_<stem>/)")
    pa.add_argument("--timeout", default=300, type=int, help="Timeout seconds for run_strategia")
    pa.set_defaults(func=cmd_autotune)

    # autotune-regimes
    pr = sub.add_parser(
        "autotune-regimes",
        help="Regime-wise autotune: one ENTRY group at a time"
    )
    pr.add_argument("--input", required=True, help="Path KPI CSV")
    pr.add_argument("--config", required=True, help="Path config_strategy.xlsx")
    pr.add_argument("--timeframe", required=True, help="Timeframe string (e.g. 30m, 1h, 1d)")
    pr.add_argument(
        "--regimes",
        default=None,
        help="Comma-separated regime/group list to test. "
             "Examples: TREND_UP,RANGE,LATERAL or G_TREND_UP,G_RANGE. "
             "If omitted all detected groups are used."
    )
    pr.add_argument("--trials", default=50, type=int, help="Number of trials per regime")
    pr.add_argument("--seed", default=42, type=int, help="Random seed")
    pr.add_argument("--train-ratio", default=0.7, type=float, help="Chronological train ratio")
    pr.add_argument("--n-min-trades", default=5, type=int, help="Hard constraint min closed trades")
    pr.add_argument(
        "--outdir",
        default=None,
        help="Optional output dir (default: _data/strategy_tuning_runs/<ts>_<stem>/)"
    )
    pr.add_argument("--timeout", default=300, type=int, help="Timeout seconds for run_strategia")
    pr.set_defaults(func=cmd_autotune_regimes)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())