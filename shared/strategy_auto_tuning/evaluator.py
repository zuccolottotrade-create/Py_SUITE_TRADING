from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import sys
from typing import Optional
import pandas as pd


# ===============================
# Result data structures
# ===============================

@dataclass
class EvalMetrics:
    profit: Optional[float]
    profit_per_trade: Optional[float]
    trade_count: Optional[int]
    max_drawdown: Optional[float]
    alpha_vs_buyhold: Optional[float]
    buy_hold_profit: Optional[float]
    extras: dict


@dataclass
class EvalResult:
    ok: bool
    error: Optional[str]
    returncode: int
    metrics: EvalMetrics
    stdout: str
    stderr: str
    artifacts_dir: Optional[Path]
    run_script: Optional[Path]


# ===============================
# Strategy Evaluator
# ===============================

class StrategyEvaluator:
    """
    Wrapper che esegue run_strategia.py e restituisce metriche strutturate.
    """

    def __init__(self, py_suite_root: Path | None = None):

        env_root = os.getenv("PY_SUITE_ROOT")

        if py_suite_root is None:
            if env_root:
                py_suite_root = Path(env_root)
            else:
                py_suite_root = Path(__file__).resolve().parents[2]

        self.py_suite_root = py_suite_root.resolve()
        self.run_script = self._find_run_script()

    # ===============================
    # Locate run_strategia.py
    # ===============================

    def _find_run_script(self) -> Path | None:

        env_script = os.getenv("PY_SUITE_RUN_STRATEGIA")
        if env_script:
            p = Path(env_script)
            if p.exists():
                return p.resolve()

        canonical = self.py_suite_root / "3. Run_strategia" / "run_strategia.py"
        if canonical.exists():
            return canonical.resolve()

        try:
            matches = list(self.py_suite_root.rglob("run_strategia.py"))
        except Exception:
            matches = []

        if matches:
            return matches[0].resolve()

        return None

    # ===============================
    # Evaluation
    # ===============================

    def evaluate(
        self,
        *,
        input_csv: Path,
        config_strategy: Path,
        timeframe: str,
        outdir: Path | None = None,
        timeout_sec: int = 300,
    ) -> EvalResult:

        input_csv = Path(input_csv)
        config_strategy = Path(config_strategy)

        if not input_csv.exists():
            return self._error(
                f"input_csv not found: {input_csv}",
                2,
                outdir,
            )

        if not config_strategy.exists():
            return self._error(
                f"config_strategy not found: {config_strategy}",
                2,
                outdir,
            )

        if self.run_script is None:
            return self._error(
                "run_strategia.py not found",
                2,
                outdir,
            )

        cmd = [sys.executable, str(self.run_script)]

        env = os.environ.copy()
        env["PY_SUITE_KPI_INPUT_CSV"] = str(input_csv)
        env["PY_SUITE_STRATEGY_FILE"] = str(config_strategy)
        env["PY_SUITE_TIMEFRAME"] = timeframe

        env["PIPELINE_MODE"] = "1"
        env["PY_SUITE_ROOT"] = str(self.py_suite_root)

        if outdir:
            env["PY_SUITE_OUT_DIR"] = str(outdir)

        try:

            stdout_path = None
            stderr_path = None

            if outdir:
                outdir.mkdir(parents=True, exist_ok=True)
                stdout_path = outdir / "stdout.txt"
                stderr_path = outdir / "stderr.txt"

            if stdout_path and stderr_path:
                with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
                    proc = subprocess.run(
                        cmd,
                        input="\n",
                        stdout=out,
                        stderr=err,
                        text=True,
                        timeout=timeout_sec,
                        env=env,
                    )
            else:
                proc = subprocess.run(
                    cmd,
                    input="\n",
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    env=env,
                )

            signal_csv = self._find_signal_csv(outdir=outdir, input_csv=input_csv)
            metrics = self._parse_metrics(signal_csv=signal_csv)

            error = None
            if proc.returncode != 0:
                error = f"run_strategia failed with returncode={proc.returncode}"
            elif signal_csv is None:
                error = "SIGNAL csv not found in evaluation outdir"

            return EvalResult(
                ok=(error is None),
                error=error,
                returncode=proc.returncode,
                metrics=metrics,
                stdout=proc.stdout,
                stderr=proc.stderr,
                artifacts_dir=outdir,
                run_script=self.run_script,
            )


        except subprocess.TimeoutExpired as exc:

            return EvalResult(
                ok=False,
                error="evaluation timeout",
                returncode=124,
                metrics=EvalMetrics(None, None, None, None, None, None, {}),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                artifacts_dir=outdir,
                run_script=self.run_script,

            )


        except Exception as exc:

            return EvalResult(
                ok=False,
                error=str(exc),
                returncode=1,
                metrics=EvalMetrics(None, None, None, None, None, None, {}),
                stdout="",
                stderr="",
                artifacts_dir=outdir,
                run_script=self.run_script,

            )

    # ===============================
    # Metrics parser
    # ===============================

    def _parse_metrics(self, signal_csv: Path | None) -> EvalMetrics:

        if signal_csv is None or not Path(signal_csv).exists():
            return EvalMetrics(None, None, None, None, None, None, {})

        df = pd.read_csv(signal_csv, sep=";", engine="python")

        for col in ["close", "Profit/Trade", "Sum Profit/Trade"]:
            if col in df.columns:
                df[col] = _series_to_float(df[col])

        profit = 0.0
        trade_count = 0
        profit_per_trade = 0.0
        buy_hold_profit = None
        alpha_vs_buyhold = None
        max_drawdown = 0.0
        extras: dict = {}

        if "Profit/Trade" in df.columns:
            trade_pnl = pd.to_numeric(df["Profit/Trade"], errors="coerce").dropna()
            profit = float(trade_pnl.sum()) if len(trade_pnl) else 0.0
            trade_count = int(trade_pnl.notna().sum()) if len(trade_pnl) else 0

            if trade_count > 0:
                profit_per_trade = float(profit / trade_count)

            equity = trade_pnl.cumsum()
            if len(equity):
                running_peak = equity.cummax()
                drawdown = running_peak - equity
                max_drawdown = float(drawdown.max()) if len(drawdown) else 0.0

        if "close" in df.columns and len(df) > 0:
            first_close = pd.to_numeric(df["close"], errors="coerce").iloc[0]
            last_close = pd.to_numeric(df["close"], errors="coerce").iloc[-1]

            if pd.notna(first_close) and pd.notna(last_close):
                buy_hold_profit = float(last_close - first_close)

        if buy_hold_profit is not None:
            alpha_vs_buyhold = float(profit - buy_hold_profit)

        # -------------------------------------------------------
        # Breakdown per regime dal SIGNAL_* finale
        # Preferiamo Entry_Regime esplicito; fallback su REGIME_L1_RAW
        # solo se Entry_Regime non è disponibile.
        # -------------------------------------------------------
        regime_col = None
        if "Entry_Regime" in df.columns:
            regime_col = "Entry_Regime"
        elif "REGIME_L1_RAW" in df.columns:
            regime_col = "REGIME_L1_RAW"
        elif "REGIME_L1" in df.columns:
            regime_col = "REGIME_L1"
        elif "REGIME_L1_CODE" in df.columns:
            regime_col = "REGIME_L1_CODE"

        if "Profit/Trade" in df.columns and regime_col is not None:
            closed_mask = pd.to_numeric(df["Profit/Trade"], errors="coerce").notna()
            closed = df.loc[closed_mask, [regime_col, "Profit/Trade"]].copy()

            if len(closed):
                closed["Profit/Trade"] = pd.to_numeric(closed["Profit/Trade"], errors="coerce")
                closed = closed.dropna(subset=["Profit/Trade"])

                by_entry_regime = {}
                for reg_key, sub in closed.groupby(regime_col, sort=True):
                    vals = pd.to_numeric(sub["Profit/Trade"], errors="coerce").dropna()
                    n = int(len(vals))
                    if n == 0:
                        continue

                    net = float(vals.sum())
                    ppt = float(net / n) if n else 0.0

                    by_entry_regime[str(reg_key)] = {
                        "profit": net,
                        "trade_count": n,
                        "profit_per_trade": ppt,
                    }

                extras["by_entry_regime"] = by_entry_regime

        return EvalMetrics(
            profit=profit,
            profit_per_trade=profit_per_trade,
            trade_count=trade_count,
            max_drawdown=max_drawdown,
            alpha_vs_buyhold=alpha_vs_buyhold,
            buy_hold_profit=buy_hold_profit,
            extras=extras,
        )


    # ===============================
    # Signal CSV discovery
    # ===============================

    def _find_signal_csv(self, outdir: Path | None, input_csv: Path) -> Path | None:
        """
        Resolve SIGNAL csv produced by the current evaluation.

        IMPORTANT:
        - If outdir is provided, search ONLY inside outdir.
          This avoids picking stale SIGNAL files from shared locations
          such as input_csv.parent (e.g. _data/Test Data).
        - Fallback to input_csv.parent is allowed only when outdir is None.
        """
        if outdir is not None:
            outdir = Path(outdir)
            if not outdir.exists():
                return None

            candidates = sorted(outdir.rglob("SIGNAL_*.csv"))
            return candidates[0] if candidates else None

        default_signal = Path(input_csv).parent / f"SIGNAL_{Path(input_csv).name}"
        if default_signal.exists():
            return default_signal

        return None
    # ===============================
    # Error result
    # ===============================
    def _error(self, msg: str, code: int, outdir: Path | None):

        return EvalResult(
            ok=False,
            error=msg,
            returncode=code,
            metrics=EvalMetrics(None, None, None, None, None, None, {}),
            stdout="",
            stderr="",
            artifacts_dir=outdir,
            run_script=self.run_script,
        )


# ===============================
# Float parser EU/US
# ===============================

def _series_to_float(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().replace({"": None, "nan": None, "None": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _to_float(text: str) -> Optional[float]:

    s = text.strip().replace(" ", "")

    if not s:
        return None

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


__all__ = ["StrategyEvaluator", "EvalResult", "EvalMetrics"]