# shared/strategy_auto_tuning/regime_forward_engine.py
"""
Regime-aware forward selection engine (v2).

Goal
- Compose a multi-regime strategy by progressively enabling regime blocks only if they improve
  the objective (default: alpha = NetProfitStrategy - BuyHold; score = -alpha).
- Optional interactive validation step per candidate regime (YES/NO).
- Writes:
  - selection_log.csv  (sep=';' EU decimals)
  - regime_summary.csv (sep=';' EU decimals)
  - best_composed.xlsx (via StrategyBuilder)

Design notes
- This module is orchestration logic. It delegates:
  - evaluation to an evaluator callable (wrapper over run_strategia.py)
  - config editing/merging to a builder callable (merge regime blocks into a composed xlsx)
- Keep the interfaces minimal and inject dependencies to avoid tight coupling.

Project standards
- CSV separator ';'
- EU decimal output (comma)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Any
import json
import math
import time


# -----------------------------
# Data contracts
# -----------------------------

@dataclass(frozen=True)
class EvalResult:
    """Minimal evaluator output needed by forward selection."""
    ok: bool
    score: float
    alpha: float
    penalty: float

    buy_hold_filo: float
    net_profit_strat: float
    n_trades_closed: int
    max_dd: float

    # Optional extras (kept as dict to avoid schema churn)
    extras: Dict[str, Any]


@dataclass(frozen=True)
class RegimeBlock:
    """Represents the tuned best block for a single regime."""
    regime: str
    best_xlsx: Path

    # Per-regime evaluation snapshot (optional; can be filled later)
    profit_trades: float = float("nan")
    profit_buyhold: float = float("nan")
    alpha_regime: float = float("nan")
    n_trades: int = 0
    max_dd: float = float("nan")


@dataclass(frozen=True)
class SelectionStep:
    step: int
    s_before: str
    candidate: str
    s_after: str

    # delta vs baseline S
    score_before: float
    score_after: float
    alpha_before: float
    alpha_after: float
    alpha_delta: float

    dd_before: float
    dd_after: float
    dd_delta: float

    trades_before: int
    trades_after: int
    trades_delta: int

    ok_after: bool
    accepted: bool
    decision: str
    reason: str

# NOTE:
# profit_trades / profit_buyhold / alpha / n_trades are intentionally left empty
# in final regime_summary until they are computed from the FINAL COMPOSED SIGNAL_*.
# This avoids mixing standalone regime metrics with composed-run metrics.
@dataclass(frozen=True)
class RegimeSummaryRow:
    regime: str
    enabled: bool
    profit_trades: float
    profit_buyhold: float
    alpha: float
    n_trades: int
    marginal_contribution: float


@dataclass(frozen=True)
class ForwardSelectionSpec:
    # candidate regimes to consider (order used only for tie-breaks / display)
    candidate_regimes: Sequence[str]

    # acceptance thresholds
    eps_alpha: float = 0.0
    dd_tolerance_ratio: float = 0.20  # allow DD to increase by up to +20% relative
    n_trades_min: int = 0

    # stop conditions
    max_regimes: int = 99

    # interactivity
    interactive: bool = True
    auto_accept: bool = False  # if True, accept any candidate that passes constraints

    # stable objective: default score already incorporates penalty; we also apply constraints here
    enforce_constraints: bool = True


# -----------------------------
# Type aliases for injected deps
# -----------------------------

# Evaluator signature:
# - input_csv: path KPI dataset
# - config_xlsx: strategy config
# - timeframe: timeframe string (must be passed, never inferred)
# - outdir: directory where evaluator writes its artifacts
EvaluatorFn = Callable[[Path, Path, str, Path], EvalResult]

# Builder signature:
# - base_config: template xlsx (contains all conditions/archetypes)
# - selected_blocks: list of RegimeBlock to enable/merge
# - out_xlsx: destination for composed strategy
StrategyBuilderFn = Callable[[Path, Sequence[RegimeBlock], Path], None]

# Trade report callback (optional):
# - eval_dir: directory containing evaluator artifacts
# - regime: candidate regime for labeling
TradeReporterFn = Callable[[Path, str], None]


# -----------------------------
# Small utilities (CSV EU formatting)
# -----------------------------

def _eu_num(x: Any) -> str:
    """Format number with EU decimal comma. Keep ints without decimals."""
    if x is None:
        return ""
    if isinstance(x, bool):
        return "True" if x else "False"
    if isinstance(x, (int,)):
        return str(x)
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return ""
        # keep a reasonable precision without scientific notation
        s = f"{x:.10f}".rstrip("0").rstrip(".")
        if s == "-0":
            s = "0"
        return s.replace(".", ",")
    # fallback
    return str(x)


def _csv_write_semicolon(path: Path, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(";".join(header) + "\n")
        for r in rows:
            f.write(";".join(_eu_num(v) for v in r) + "\n")


def _now_ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def _join_regimes(rs: Sequence[str]) -> str:
    return "+".join(rs) if rs else "{}"


# -----------------------------
# Core engine
# -----------------------------

CANONICAL_REGIME_GROUPS = {
    "G_RANGE",
    "G_LATERAL",
    "G_VOLATILE",
    "G_TREND_UP",
    "G_TREND_DOWN",
}

LEGACY_EXCLUDED_REGIME_GROUPS = {
    "G_TREND",
}

def _filter_operational_candidates(groups: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()

    for g in groups:
        gs = str(g).strip().upper()
        if not gs:
            continue
        if gs in LEGACY_EXCLUDED_REGIME_GROUPS:
            continue
        if gs not in CANONICAL_REGIME_GROUPS:
            continue
        if gs in seen:
            continue
        seen.add(gs)
        out.append(gs)

    return out

class RegimeForwardEngine:
    """
    Forward selection over regimes.

    You provide:
    - base_config_xlsx: the archetype/template xlsx
    - tuned_blocks: map regime -> RegimeBlock(best.xlsx tuned for that regime)
    - evaluator: wrapper that runs run_strategia.py and returns EvalResult
    - builder: merges selected blocks into a composed xlsx
    """

    def __init__(
        self,
        evaluator: EvaluatorFn,
        builder: StrategyBuilderFn,
        trade_reporter: Optional[TradeReporterFn] = None,
    ) -> None:
        self._evaluator = evaluator
        self._builder = builder
        self._trade_reporter = trade_reporter

    def run(
        self,
        *,
        input_csv: Path,
        timeframe: str,
        base_config_xlsx: Path,
        tuned_blocks: Dict[str, RegimeBlock],
        outdir: Path,
        spec: ForwardSelectionSpec,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Execute forward selection.

        Returns a dict with:
          - selected_regimes
          - rejected_regimes
          - best_composed_xlsx
          - selection_log_csv
          - regime_summary_csv
        """
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        raw_candidate_regimes = list(spec.candidate_regimes)
        legacy_present = [
            str(g).strip().upper()
            for g in raw_candidate_regimes
            if str(g).strip().upper() in LEGACY_EXCLUDED_REGIME_GROUPS
        ]
        if legacy_present:
            print(
                "[INFO] Ignoro gruppi legacy non operativi: "
                + ", ".join(sorted(set(legacy_present)))
            )

        candidate_regimes = _filter_operational_candidates(raw_candidate_regimes)

        # runspec (minimal)
        runspec = {
            "ts": _now_ts(),
            "seed": seed,
            "timeframe": timeframe,
            "input_csv": str(Path(input_csv)),
            "base_config_xlsx": str(Path(base_config_xlsx)),
            "candidate_regimes": list(candidate_regimes),
            "candidate_regimes_raw": list(spec.candidate_regimes),
            "eps_alpha": spec.eps_alpha,
            "dd_tolerance_ratio": spec.dd_tolerance_ratio,
            "n_trades_min": spec.n_trades_min,
            "interactive": spec.interactive,
            "auto_accept": spec.auto_accept,
        }
        (outdir / "runspec.json").write_text(json.dumps(runspec, indent=2), encoding="utf-8")
        # Baseline = evaluate composed strategy with S = {}
        selected: List[str] = []
        joint_opt: List[str] = []
        rejected: List[str] = []
        steps: List[SelectionStep] = []

        baseline_eval_dir = outdir / "selection" / "eval_baseline"
        baseline_xlsx = outdir / "selection" / "baseline_composed.xlsx"
        self._builder(base_config_xlsx, [], baseline_xlsx)
        baseline = self._evaluator(input_csv, baseline_xlsx, timeframe, baseline_eval_dir)

        current = baseline
        current_xlsx = baseline_xlsx

        # Summary rows (filled at end)
        summary_rows: Dict[str, RegimeSummaryRow] = {}

        # Helper: constraint check for accepting a candidate
        def passes_constraints(before: EvalResult, after: EvalResult) -> Tuple[bool, str]:
            if not after.ok:
                return False, "evaluator_not_ok"
            if spec.enforce_constraints:
                if after.alpha < before.alpha + spec.eps_alpha:
                    return False, f"alpha_not_improving_eps({spec.eps_alpha})"
                if after.n_trades_closed < spec.n_trades_min:
                    return False, f"n_trades_below_min({spec.n_trades_min})"
                # DD tolerance relative to before (allow +dd_tolerance_ratio)
                # If before DD is 0, allow any DD up to a small absolute threshold
                if before.max_dd > 0:
                    if after.max_dd > before.max_dd * (1.0 + spec.dd_tolerance_ratio):
                        return False, f"dd_increase_above_tolerance({spec.dd_tolerance_ratio})"
            return True, "ok"

        def standalone_is_credible(block: RegimeBlock) -> bool:
            if block is None:
                return False
            if block.n_trades <= 0:
                return False
            if not math.isfinite(block.profit_trades):
                return False
            if block.profit_trades <= 0:
                return False
            return True

        def classify_rejection(before: EvalResult, after: EvalResult, regime: str, rejection_reason: str) -> Tuple[str, bool, str]:
            """
            Returns: (decision, accepted, reason)
            decision ∈ {PROMOTE, KEEP_FOR_JOINT_OPT, DROP_HARD}
            """
            block = tuned_blocks.get(regime)

            if rejection_reason.startswith("alpha_not_improving_eps("):
                if standalone_is_credible(block):
                    return "KEEP_FOR_JOINT_OPT", False, "alpha_not_improving_keep_for_joint_opt"
                return "DROP_HARD", False, "alpha_not_improving_and_standalone_weak"

            if rejection_reason.startswith("n_trades_below_min("):
                return "DROP_HARD", False, rejection_reason

            if rejection_reason.startswith("dd_increase_above_tolerance("):
                if standalone_is_credible(block):
                    return "KEEP_FOR_JOINT_OPT", False, "dd_above_tolerance_keep_for_joint_opt"
                return "DROP_HARD", False, rejection_reason

            if rejection_reason == "evaluator_not_ok":
                return "DROP_HARD", False, rejection_reason

            if standalone_is_credible(block):
                return "KEEP_FOR_JOINT_OPT", False, f"{rejection_reason}_keep_for_joint_opt"

            return "DROP_HARD", False, rejection_reason

        # Loop
        step_idx = 0

        remaining = [r for r in candidate_regimes if r in tuned_blocks]

        while remaining and len(selected) < spec.max_regimes:
            # Evaluate all candidates not yet selected/rejected
            candidates = [
                r for r in remaining
                if (r not in selected and r not in joint_opt and r not in rejected)
            ]
            if not candidates:
                break

            ranked_candidates: List[Tuple[str, EvalResult, Path, Path]] = []

            for r in candidates:
                # compose S ∪ {r}
                composed_xlsx = outdir / "selection" / "candidates" / f"candidate_{step_idx:02d}_{_join_regimes(selected+[r])}.xlsx"
                eval_dir = outdir / "selection" / "eval" / f"step_{step_idx:02d}_{r}"
                self._builder(base_config_xlsx, [tuned_blocks[x] for x in (selected + [r])], composed_xlsx)

                res = self._evaluator(input_csv, composed_xlsx, timeframe, eval_dir)
                ranked_candidates.append((r, res, eval_dir, composed_xlsx))

            if not ranked_candidates:
                break

            ranked_candidates.sort(key=lambda x: x[1].score, reverse=True)

            chosen_r: Optional[str] = None
            chosen_eval: Optional[EvalResult] = None
            chosen_eval_dir: Optional[Path] = None
            chosen_xlsx_path: Optional[Path] = None
            chosen_ok_constraints = False
            chosen_reason = "no_candidate_evaluated"
            chosen_decision = "DROP_HARD"
            accepted = False

            fallback_r, fallback_eval, fallback_eval_dir, fallback_xlsx_path = ranked_candidates[0]

            for r, res, eval_dir, composed_xlsx in ranked_candidates:
                ok_constraints, reason_constraints = passes_constraints(current, res)

                if not ok_constraints:
                    continue

                # show trade report (optional) before asking user
                if self._trade_reporter is not None:
                    try:
                        self._trade_reporter(eval_dir, r)
                    except Exception:
                        # do not fail selection due to reporting
                        pass

                candidate_accepted = False
                candidate_reason = reason_constraints

                if spec.auto_accept and not spec.interactive:
                    candidate_accepted = True
                    candidate_reason = "auto_accept_noninteractive"
                elif spec.auto_accept and spec.interactive:
                    # keep deterministic: auto_accept overrides user interaction
                    candidate_accepted = True
                    candidate_reason = "auto_accept"
                elif spec.interactive:
                    candidate_accepted = self._ask_user_accept(r, current, res)
                    candidate_reason = "user_yes" if candidate_accepted else "user_no"
                else:
                    # non-interactive and not auto-accept: accept if improves
                    candidate_accepted = True
                    candidate_reason = "accepted_noninteractive"

                chosen_r = r
                chosen_eval = res
                chosen_eval_dir = eval_dir
                chosen_xlsx_path = composed_xlsx
                chosen_ok_constraints = ok_constraints
                chosen_reason = candidate_reason
                chosen_decision = "PROMOTE"
                accepted = candidate_accepted

                if candidate_accepted:
                    break

            if chosen_r is None or chosen_eval is None or chosen_eval_dir is None or chosen_xlsx_path is None:
                # Nessun candidato passa i constraint:
                # usa il best-by-score come fallback per log e classificazione.
                chosen_r = fallback_r
                chosen_eval = fallback_eval
                chosen_eval_dir = fallback_eval_dir
                chosen_xlsx_path = fallback_xlsx_path
                chosen_ok_constraints, chosen_reason = passes_constraints(current, chosen_eval)
                chosen_decision, accepted, chosen_reason = classify_rejection(
                    current,
                    chosen_eval,
                    chosen_r,
                    chosen_reason,
                )

                # show trade report (optional) before asking user
                if self._trade_reporter is not None:
                    try:
                        self._trade_reporter(chosen_eval_dir, chosen_r)
                    except Exception:
                        # do not fail selection due to reporting
                        pass

            if spec.interactive and chosen_decision == "KEEP_FOR_JOINT_OPT":
                accepted = self._ask_user_accept_constraints_override(
                    chosen_r,
                    current,
                    chosen_eval,
                    chosen_reason,
                )
                if accepted:
                    chosen_reason = "user_override_constraints"
                else:
                    chosen_decision = "DROP_HARD"
                    chosen_reason = "user_rejected_joint_opt"

            # Log step
            s_after_list = list(selected)
            if chosen_decision == "PROMOTE" and accepted:
                s_after_list.append(chosen_r)
            elif chosen_decision == "KEEP_FOR_JOINT_OPT":
                s_after_list.append(f"{chosen_r}[JOINT]")

            step = SelectionStep(
                step=step_idx + 1,
                s_before=_join_regimes(selected),
                candidate=chosen_r,
                s_after=_join_regimes(s_after_list),
                score_before=current.score,
                score_after=chosen_eval.score,
                alpha_before=current.alpha,
                alpha_after=chosen_eval.alpha,
                alpha_delta=chosen_eval.alpha - current.alpha,
                dd_before=current.max_dd,
                dd_after=chosen_eval.max_dd,
                dd_delta=chosen_eval.max_dd - current.max_dd,
                trades_before=current.n_trades_closed,
                trades_after=chosen_eval.n_trades_closed,
                trades_delta=chosen_eval.n_trades_closed - current.n_trades_closed,
                ok_after=chosen_eval.ok,
                accepted=accepted,
                decision=chosen_decision,
                reason=chosen_reason,
            )
            steps.append(step)

            # Apply decision
            if chosen_decision == "PROMOTE" and accepted:
                if chosen_r not in selected:
                    selected.append(chosen_r)
                current = chosen_eval
                current_xlsx = chosen_xlsx_path
            elif chosen_decision == "KEEP_FOR_JOINT_OPT":
                if chosen_r not in joint_opt:
                    joint_opt.append(chosen_r)
            else:
                if chosen_r not in rejected:
                    rejected.append(chosen_r)

            # Stopping rule:
            # stop only on hard drop / no viable continuation.
            # KEEP_FOR_JOINT_OPT must not terminate the screening loop.
            if not accepted and chosen_decision == "DROP_HARD":
                break

            step_idx += 1
            continue

        # Write best composed artifact
        best_composed_xlsx = outdir / "selection" / "best_composed.xlsx"
        final_regimes_for_build: List[str] = []
        seen_final: set[str] = set()
        for r in _filter_operational_candidates(list(selected) + list(joint_opt)):
            if r not in seen_final:
                seen_final.add(r)
                final_regimes_for_build.append(r)

        self._builder(
            base_config_xlsx,
            [tuned_blocks[r] for r in final_regimes_for_build],
            best_composed_xlsx,
        )

        # Evaluate final composed (for final_report)
        final_eval_dir = outdir / "final_report"
        final_eval = self._evaluator(input_csv, best_composed_xlsx, timeframe, final_eval_dir)

        # Build regime summary from FINAL COMPOSED evaluation.
        # IMPORTANT:
        # - do not reuse standalone per-regime metrics stored in RegimeBlock here,
        #   because they refer to isolated regime evaluations and can mismatch
        #   against the final composed strategy metrics.
        mc_by_regime: Dict[str, float] = {}
        for st in steps:
            if st.accepted:
                mc_by_regime[st.candidate] = st.alpha_delta

        by_entry_regime: Dict[str, Any] = {}
        final_eval_extras = getattr(final_eval, "extras", {}) or {}
        if isinstance(final_eval_extras, dict):
            by_entry_regime = final_eval_extras.get("by_entry_regime", {}) or {}

        regime_to_entry_label = {
            "G_RANGE": "RANGE",
            "G_LATERAL": "LATERAL",
            "G_TREND_UP": "TREND_UP",
            "G_TREND_DOWN": "TREND_DOWN",
        }

        for r in candidate_regimes:
            enabled = r in final_regimes_for_build
            mc = mc_by_regime.get(r, 0.0)

            entry_label = regime_to_entry_label.get(r)
            regime_stats = by_entry_regime.get(entry_label, {}) if entry_label else {}

            profit_trades = regime_stats.get("profit", float("nan"))
            n_trades = int(regime_stats.get("trade_count", 0)) if regime_stats else 0

            summary_rows[r] = RegimeSummaryRow(
                regime=r,
                enabled=enabled,
                profit_trades=profit_trades,
                profit_buyhold=float("nan"),
                alpha=float("nan"),
                n_trades=n_trades,
                marginal_contribution=mc,
            )

        # Write selection_log.csv
        selection_log_csv = outdir / "selection" / "selection_log.csv"
        _csv_write_semicolon(
            selection_log_csv,
            header=[
                "step",
                "S_before",
                "candidate",
                "S_after",
                "score_before",
                "score_after",
                "alpha_before",
                "alpha_after",
                "alpha_delta",
                "dd_before",
                "dd_after",
                "dd_delta",
                "trades_before",
                "trades_after",
                "trades_delta",
                "ok_after",
                "accepted",
                "decision",
                "reason",
            ],
            rows=[
                [
                    s.step,
                    s.s_before,
                    s.candidate,
                    s.s_after,
                    s.score_before,
                    s.score_after,
                    s.alpha_before,
                    s.alpha_after,
                    s.alpha_delta,
                    s.dd_before,
                    s.dd_after,
                    s.dd_delta,
                    s.trades_before,
                    s.trades_after,
                    s.trades_delta,
                    s.ok_after,
                    s.accepted,
                    s.decision,
                    s.reason,
                ]
                for s in steps
            ],
        )

        # Write regime_summary.csv
        regime_summary_csv = outdir / "selection" / "regime_summary.csv"
        _csv_write_semicolon(
            regime_summary_csv,
            header=[
                "regime",
                "enabled",
                "profit_trades",
                "profit_buyhold",
                "alpha",
                "n_trades",
                "marginal_contribution",
            ],
            rows=[
                [
                    row.regime,
                    row.enabled,
                    row.profit_trades,
                    row.profit_buyhold,
                    row.alpha,
                    row.n_trades,
                    row.marginal_contribution,
                ]
                for row in (summary_rows[r] for r in candidate_regimes if r in summary_rows)
            ],
        )

        # Persist a compact JSON result (useful for cli.py)
        result_json = outdir / "selection" / "selection_result.json"
        result_payload = {
            "selected_regimes": selected,
            "joint_opt_regimes": joint_opt,
            "rejected_regimes": rejected,
            "final_regimes_for_build": final_regimes_for_build,
            "baseline": asdict(baseline),
            "final_eval": asdict(final_eval),
            "best_composed_xlsx": str(best_composed_xlsx),
            "selection_log_csv": str(selection_log_csv),
            "regime_summary_csv": str(regime_summary_csv),
            "evaluation_semantics": "v3_full_dataset_target_entries_only_for_per_regime_blocks",
        }
        result_json.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        return result_payload

    # -----------------------------
    # Interactive prompt
    # -----------------------------

    def _ask_user_accept(self, regime: str, before: EvalResult, after: EvalResult) -> bool:
        """
        Ask the user if they want to enable trading for the regime.

        This method intentionally prints a compact summary only.
        Detailed trade list printing should be done by trade_reporter, if provided.
        """
        print("")
        print("=== REGIME PROPOSAL ===")
        print(f"Regime: {regime}")
        print(f"Alpha before: {_eu_num(before.alpha)}  | Alpha after: {_eu_num(after.alpha)}  | Delta: {_eu_num(after.alpha - before.alpha)}")
        print(f"Score before: {_eu_num(before.score)}  | Score after: {_eu_num(after.score)}")
        print(f"DD before: {_eu_num(before.max_dd)}     | DD after: {_eu_num(after.max_dd)}")
        print(f"Trades before: {before.n_trades_closed} | Trades after: {after.n_trades_closed}")
        print("")
        while True:
            print("Abilitare il trading per questo regime? [y/n]", flush=True)
            ans = input("> ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            print("Risposta non valida. Inserisci 'y' oppure 'n'.")

    def _ask_user_accept_dd_override(
        self,
        regime: str,
        before: EvalResult,
        after: EvalResult,
        rejection_reason: str,
    ) -> bool:
        """
        Ask the user whether to override a DD-only rejection.

        Used only when the candidate improves alpha/score and remains evaluator-ok,
        but exceeds the configured DD tolerance.
        """
        print("")
        print("=== REGIME PROPOSAL (DD OVERRIDE) ===")
        print(f"Regime: {regime}")
        print(f"Motivo blocco automatico: {rejection_reason}")
        print(
            f"Alpha before: {_eu_num(before.alpha)}  | "
            f"Alpha after: {_eu_num(after.alpha)}  | "
            f"Delta: {_eu_num(after.alpha - before.alpha)}"
        )
        print(
            f"Score before: {_eu_num(before.score)}  | "
            f"Score after: {_eu_num(after.score)}"
        )
        print(
            f"DD before: {_eu_num(before.max_dd)}     | "
            f"DD after: {_eu_num(after.max_dd)}     | "
            f"Delta: {_eu_num(after.max_dd - before.max_dd)}"
        )
        print(
            f"Trades before: {before.n_trades_closed} | "
            f"Trades after: {after.n_trades_closed} | "
            f"Delta: {after.n_trades_closed - before.n_trades_closed}"
        )
        print("")
        while True:
            print(
                "Accettare comunque questo regime nonostante il drawdown più alto? [y/n]",
                flush=True,
            )
            ans = input("> ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            print("Risposta non valida. Inserisci 'y' oppure 'n'.")

    def _ask_user_accept_constraints_override(
        self,
        regime: str,
        before: EvalResult,
        after: EvalResult,
        rejection_reason: str,
    ) -> bool:
        """
        Ask the user whether to override a generic constraint rejection.

        Used when no candidate in the current step passes the automatic policy,
        but we still want to give the user the option to accept the best-by-score
        candidate explicitly.
        """
        print("")
        print("=== REGIME PROPOSAL (POLICY OVERRIDE) ===")
        print(f"Regime: {regime}")
        print(f"Motivo blocco automatico: {rejection_reason}")
        print(
            f"Alpha before: {_eu_num(before.alpha)}  | "
            f"Alpha after: {_eu_num(after.alpha)}  | "
            f"Delta: {_eu_num(after.alpha - before.alpha)}"
        )
        print(
            f"Score before: {_eu_num(before.score)}  | "
            f"Score after: {_eu_num(after.score)}"
        )
        print(
            f"DD before: {_eu_num(before.max_dd)}     | "
            f"DD after: {_eu_num(after.max_dd)}     | "
            f"Delta: {_eu_num(after.max_dd - before.max_dd)}"
        )
        print(
            f"Trades before: {before.n_trades_closed} | "
            f"Trades after: {after.n_trades_closed} | "
            f"Delta: {after.n_trades_closed - before.n_trades_closed}"
        )
        print("")
        while True:
            print("Accettare comunque questo regime in deroga alla policy? [y/n]", flush=True)
            ans = input("> ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            print("Risposta non valida. Inserisci 'y' oppure 'n'.")
# -----------------------------
# Convenience wrapper (for engine.py)
# -----------------------------

def run_regime_forward_selection(
    *,
    evaluator: EvaluatorFn,
    builder: StrategyBuilderFn,
    trade_reporter: Optional[TradeReporterFn],
    input_csv: Path,
    timeframe: str,
    base_config_xlsx: Path,
    tuned_blocks: Dict[str, RegimeBlock],
    outdir: Path,
    spec: ForwardSelectionSpec,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Functional wrapper to run the engine without instantiating the class externally.
    """
    eng = RegimeForwardEngine(evaluator=evaluator, builder=builder, trade_reporter=trade_reporter)
    return eng.run(
        input_csv=Path(input_csv),
        timeframe=str(timeframe),
        base_config_xlsx=Path(base_config_xlsx),
        tuned_blocks=tuned_blocks,
        outdir=Path(outdir),
        spec=spec,
        seed=seed,
    )