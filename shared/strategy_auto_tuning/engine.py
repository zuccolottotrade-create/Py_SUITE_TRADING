# shared/strategy_auto_tuning/engine.py
"""
Strategy Auto-Tuning — Engine (V1)

End-to-end Random Search:
- Build space from TUNING
- Sample N trials
- Mutate only TUNING -> trial config xlsx
- Evaluate via run_strategia.py (StrategyEvaluator)
- Compute objective score
- Record trials.csv
- Save best.xlsx
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import csv
import json
import pandas as pd

from .evaluator import StrategyEvaluator
from .mutator import write_trial_config
from .space import build_space_from_tuning
from .samplers import RandomSearchSampler
from .objectives import ObjectiveSpec, compute_objective
from .regime_forward_engine import (
    EvalResult,
    ForwardSelectionSpec,
    RegimeBlock,
    run_regime_forward_selection,
)

from .io_config import read_tuning_sheet, write_tuning_sheet
import re
import shutil
from openpyxl import load_workbook

@dataclass(frozen=True)
class RunSpec:
    input_csv: str
    config_strategy: str
    timeframe: str
    trials: int
    seed: int
    outdir: str
    n_min_trades: int
    active_group: Optional[str] = None


@dataclass(frozen=True)
class RegimeRunSpec:
    input_csv: str
    config_strategy: str
    timeframe: str
    trials_per_regime: int
    seed: int
    outdir: str
    n_min_trades: int
    train_ratio: float
    detected_entry_groups: List[str]
    target_groups: List[str]

@dataclass(frozen=True)
class TrialRow:
    trial_id: int
    score: float
    alpha_vs_buyhold: Optional[float]
    penalty: float
    ok: bool
    reason: Optional[str]
    profit: Optional[float]
    profit_per_trade: Optional[float]
    trade_count: Optional[int]
    max_drawdown: Optional[float]
    buy_hold_profit: Optional[float]
    trial_config_xlsx: str
    eval_dir: str


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def default_outdir(base_config: Path) -> Path:
    stem = base_config.stem
    return Path("_data") / "strategy_tuning_runs" / f"{_ts()}_{stem}"
# ===============================
# EU number formatting helpers
# ===============================

_EU_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")

def _fmt_eu_num(v: Any) -> Any:
    """
    Convert numbers to EU decimal comma representation.
    12.34 -> "12,34"
    """
    if v is None:
        return v

    if isinstance(v, bool):
        return v

    if isinstance(v, (int, float)):
        s = f"{v}"
        if "e" in s.lower():
            s = f"{v:.12f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")

    if isinstance(v, str):
        s = v.strip()
        if _EU_DECIMAL_RE.match(s):
            return s.replace(".", ",")
        return v

    return v


def _normalize_candidate_values_cell(v: Any) -> Any:
    """
    candidate_values:
    - '|' -> ';'
    - decimal '.' -> ','
    """
    if v is None:
        return v

    s = str(v).strip()

    if not s:
        return v

    s = s.replace("|", ";")

    parts = [p.strip() for p in s.split(";")]
    out = []

    for p in parts:
        out.append(str(_fmt_eu_num(p)))

    return ";".join(out)


def _normalize_best_xlsx(best_path: Path) -> None:
    """
    Normalize TUNING.candidate_values in best.xlsx
    """
    wb = load_workbook(best_path)

    if "TUNING" not in wb.sheetnames:
        wb.close()
        return

    ws = wb["TUNING"]

    header = [c.value for c in ws[1]]

    try:
        idx = header.index("candidate_values") + 1
    except ValueError:
        wb.close()
        return

    for r in range(2, ws.max_row + 1):
        c = ws.cell(row=r, column=idx)
        c.value = _normalize_candidate_values_cell(c.value)

    wb.save(best_path)
    wb.close()

def _safe_group_dirname(group_name: str) -> str:
    s = str(group_name).strip()
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s or "UNKNOWN_GROUP"


def _read_conditions_rows(config_strategy: Path) -> Tuple[Any, List[str], Dict[str, int], List[Dict[str, Any]]]:
    p = Path(config_strategy)

    try:
        with open(p, "rb") as fh:
            sig = fh.read(8)
    except Exception:
        sig = None


    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = load_workbook(p)
    except InvalidFileException as e:
        raise RuntimeError(
            f"load_workbook failed for config_strategy={p} "
            f"(suffix={p.suffix!r}, size={p.stat().st_size if p.exists() else None}, sig={sig!r})"
        ) from e

    if "CONDITIONS" not in wb.sheetnames:
        wb.close()
        raise ValueError("Missing CONDITIONS sheet in config_strategy")

    ws = wb["CONDITIONS"]
    header = [c.value for c in ws[1]]
    idx = {str(name): i + 1 for i, name in enumerate(header) if name is not None}

    required = ["id", "enabled", "scope", "side", "group"]
    missing = [c for c in required if c not in idx]
    if missing:
        wb.close()
        raise ValueError(f"Missing CONDITIONS columns: {missing}")

    rows: List[Dict[str, Any]] = []
    for r in range(2, ws.max_row + 1):
        row: Dict[str, Any] = {}
        for col_name, col_idx in idx.items():
            row[col_name] = ws.cell(row=r, column=col_idx).value
        rows.append(row)

    return wb, header, idx, rows


def _is_truthy_enabled(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _normalize_scope(v: Any) -> str:
    return str(v).strip().upper() if v is not None else ""


def _normalize_side(v: Any) -> str:
    return str(v).strip().upper() if v is not None else ""


def _normalize_group(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def detect_entry_groups(config_strategy: Path) -> List[str]:
    wb, _header, _idx, rows = _read_conditions_rows(config_strategy)
    try:
        groups: List[str] = []
        seen = set()

        for row in rows:
            enabled = _is_truthy_enabled(row.get("enabled"))
            scope = _normalize_scope(row.get("scope"))
            side = _normalize_side(row.get("side"))
            group = _normalize_group(row.get("group"))

            if not enabled:
                continue
            if scope != "ENTRY":
                continue
            if side not in {"LONG", "SHORT", "BOTH", ""}:
                continue
            if not group:
                continue

            if group not in seen:
                seen.add(group)
                groups.append(group)

        return groups
    finally:
        wb.close()
def _decision_hint(
    *,
    trade_count: Any,
    alpha_vs_buyhold: Any,
    n_min_trades: int,
) -> str:
    try:
        tc = 0 if trade_count is None else int(float(str(trade_count).replace(",", ".")))
    except Exception:
        tc = 0

    try:
        alpha = None if alpha_vs_buyhold is None else float(str(alpha_vs_buyhold).replace(",", "."))
    except Exception:
        alpha = None

    if tc <= 0:
        return "DROP"

    if tc < int(n_min_trades):
        return "REVIEW"

    if alpha is None:
        return "REVIEW"

    if alpha > 0:
        return "KEEP"

    return "DROP"

def _write_masked_conditions_config(
    *,
    base_config_path: Path,
    out_config_path: Path,
    active_entry_group: str,
) -> None:
    wb = load_workbook(base_config_path)
    if "CONDITIONS" not in wb.sheetnames:
        wb.close()
        raise ValueError("Missing CONDITIONS sheet in config_strategy")

    ws = wb["CONDITIONS"]
    header = [c.value for c in ws[1]]
    idx = {str(name): i + 1 for i, name in enumerate(header) if name is not None}

    required = ["enabled", "scope", "group"]
    missing = [c for c in required if c not in idx]
    if missing:
        wb.close()
        raise ValueError(f"Missing CONDITIONS columns: {missing}")

    for r in range(2, ws.max_row + 1):
        scope = _normalize_scope(ws.cell(r, idx["scope"]).value)
        group = _normalize_group(ws.cell(r, idx["group"]).value)

        if scope == "ENTRY":
            ws.cell(r, idx["enabled"]).value = (group == active_entry_group)
        elif scope == "EXIT":
            ws.cell(r, idx["enabled"]).value = (group == active_entry_group) or (group == "G_ANY")
        else:
            ws.cell(r, idx["enabled"]).value = False

    out_config_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_config_path)
    wb.close()

def _write_forward_composed_conditions_config(
    *,
    base_config_path: Path,
    out_config_path: Path,
    active_groups: List[str],
) -> None:
    """
    Build a composed strategy config from the external base template.

    Semantics:
    - keep global groups (e.g. G_ANY) always enabled
    - enable rows whose CONDITIONS.group belongs to active_groups
    - disable all other rows
    """
    wb = load_workbook(base_config_path)
    if "CONDITIONS" not in wb.sheetnames:
        wb.close()
        raise ValueError("Missing CONDITIONS sheet in config_strategy")

    ws = wb["CONDITIONS"]
    header = [c.value for c in ws[1]]
    idx = {str(name): i + 1 for i, name in enumerate(header) if name is not None}

    required = ["enabled", "group"]
    missing = [c for c in required if c not in idx]
    if missing:
        wb.close()
        raise ValueError(f"Missing CONDITIONS columns: {missing}")

    normalized_active = {
        _normalize_group(g).upper()
        for g in (active_groups or [])
        if _normalize_group(g)
    }

    for r in range(2, ws.max_row + 1):
        group_raw = ws.cell(r, idx["group"]).value
        group_norm = _normalize_group(group_raw)
        group_upper = group_norm.upper()

        keep_enabled = False
        if _is_global_group(group_norm):
            keep_enabled = True
        elif group_upper in normalized_active:
            keep_enabled = True

        ws.cell(r, idx["enabled"]).value = keep_enabled

    out_config_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_config_path)
    wb.close()
def _merge_forward_tuning_from_blocks(
    *,
    base_config_path: Path,
    selected_blocks: List[RegimeBlock],
    out_config_path: Path,
) -> None:
    """
    Merge TUNING sheet values from selected per-regime best.xlsx files into a composed config.

    Strategy:
    - start from TUNING of base_config_path
    - for each selected block, read TUNING from block.best_xlsx
    - merge rows by parameter id (column 'param_name' if present, else 'id')
    - for overlapping parameter ids, later blocks override earlier ones
    - write merged TUNING into out_config_path, preserving all non-TUNING sheets
    """
    if not selected_blocks:
        return

    base_df = read_tuning_sheet(base_config_path).copy()

    key_col = None
    for c in ("param_name", "id"):
        if c in base_df.columns:
            key_col = c
            break
    if key_col is None:
        raise ValueError("TUNING sheet missing key column 'param_name' or 'id'")

    merged_df = base_df.copy()
    merged_df[key_col] = merged_df[key_col].astype(str)

    for block in selected_blocks:
        block_df = read_tuning_sheet(block.best_xlsx).copy()
        if key_col not in block_df.columns:
            raise ValueError(
                f"TUNING sheet in {block.best_xlsx.name} missing key column '{key_col}'"
            )

        block_df[key_col] = block_df[key_col].astype(str)

        # Use block rows as authoritative for matching parameter ids
        block_map = block_df.set_index(key_col)
        merged_df = merged_df.set_index(key_col)

        common_keys = [k for k in merged_df.index if k in block_map.index]
        for k in common_keys:
            for col in merged_df.columns:
                if col in block_map.columns:
                    merged_df.at[k, col] = block_map.at[k, col]

        merged_df = merged_df.reset_index()

    write_tuning_sheet(
        base_xlsx_path=out_config_path,
        tuning_df=merged_df,
        out_xlsx_path=out_config_path,
    )


def _is_global_group(group_value: Any) -> bool:
    """
    Global/non-regime groups that should remain enabled even when the
    forward-selection baseline represents S = {}.

    Convention:
    - keep G_ANY active
    - empty group is treated as non-global here (disabled by default)
    """
    g = _normalize_group(group_value).upper()
    return g in {"G_ANY"}


def _write_forward_baseline_config(
    *,
    base_config_path: Path,
    out_config_path: Path,
) -> None:
    """
    Build the true forward-selection baseline S = {}.

    Semantics:
    - disable every regime-specific CONDITION row
    - keep enabled only global rows (currently group == G_ANY)
    - preserve all non-CONDITIONS sheets as-is
    """
    wb = load_workbook(base_config_path)
    if "CONDITIONS" not in wb.sheetnames:
        wb.close()
        raise ValueError("Missing CONDITIONS sheet in config_strategy")

    ws = wb["CONDITIONS"]
    header = [c.value for c in ws[1]]
    idx = {str(name): i + 1 for i, name in enumerate(header) if name is not None}

    required = ["enabled", "group"]
    missing = [c for c in required if c not in idx]
    if missing:
        wb.close()
        raise ValueError(f"Missing CONDITIONS columns: {missing}")

    for r in range(2, ws.max_row + 1):
        group = ws.cell(r, idx["group"]).value
        ws.cell(r, idx["enabled"]).value = _is_global_group(group)

    out_config_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_config_path)
    wb.close()


def run_autotune_v1(
        *,
        input_csv: Path,
        config_strategy: Path,
        timeframe: str,
        trials: int = 50,
        seed: int = 42,
        outdir: Optional[Path] = None,
        n_min_trades: int = 5,
        timeout_sec: int = 300,
        active_group: Optional[str] = None,
        trial_label: Optional[str] = None,
) -> Path:
    input_csv = Path(input_csv)
    config_strategy = Path(config_strategy)
    if outdir is None:
        outdir = default_outdir(config_strategy)

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # dirs
    trials_dir = outdir / "trials"
    eval_dir_root = outdir / "eval"
    trials_dir.mkdir(exist_ok=True)
    eval_dir_root.mkdir(exist_ok=True)

    runspec = RunSpec(
        input_csv=str(input_csv),
        config_strategy=str(config_strategy),
        timeframe=timeframe,
        trials=int(trials),
        seed=int(seed),
        outdir=str(outdir),
        n_min_trades=int(n_min_trades),
        active_group=active_group,
    )

    (outdir / "runspec.json").write_text(json.dumps(asdict(runspec), indent=2), encoding="utf-8")

    # build space + sampler
    space = build_space_from_tuning(config_strategy, active_group=active_group)

    if not space.params:
        print(f"[WARN] No tunable parameters for group={active_group}. Running baseline evaluation.")

        evaluator = StrategyEvaluator()

        eval_dir = outdir / "eval_baseline"
        eval_dir.mkdir(parents=True, exist_ok=True)

        ev = evaluator.evaluate(
            input_csv=input_csv,
            config_strategy=config_strategy,
            timeframe=timeframe,
            outdir=eval_dir,
            timeout_sec=timeout_sec,
        )

        obj_spec = ObjectiveSpec(
            n_min_trades=n_min_trades,
            drawdown_weight=0.5,
        )

        obj = compute_objective(ev.metrics, obj_spec)

        trials_csv = outdir / "trials.csv"

        fieldnames = [
            "trial_id",
            "score",
            "alpha_vs_buyhold",
            "penalty",
            "ok",
            "reason",
            "profit",
            "profit_per_trade",
            "trade_count",
            "max_drawdown",
            "buy_hold_profit",
            "trial_config_xlsx",
            "eval_dir",
        ]

        with trials_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            w.writeheader()

            row = {
                "trial_id": 0,
                "score": obj.score,
                "alpha_vs_buyhold": obj.alpha_vs_buyhold,
                "penalty": obj.penalty,
                "ok": obj.ok,
                "reason": obj.reason,
                "profit": ev.metrics.profit,
                "profit_per_trade": ev.metrics.profit_per_trade,
                "trade_count": ev.metrics.trade_count,
                "max_drawdown": ev.metrics.max_drawdown,
                "buy_hold_profit": ev.metrics.buy_hold_profit,
                "trial_config_xlsx": str(config_strategy),
                "eval_dir": str(eval_dir),
            }

            w.writerow({k: _fmt_eu_num(v) for k, v in row.items()})

        best_path = outdir / "best.xlsx"
        best_path.write_bytes(config_strategy.read_bytes())

        try:
            _normalize_best_xlsx(best_path)
        except Exception:
            pass


        return outdir

    sampler = RandomSearchSampler(seed=seed)
    obj_spec = ObjectiveSpec(
        n_min_trades=n_min_trades,
        drawdown_weight=0.5,
    )

    evaluator = StrategyEvaluator()

    # open trials.csv
    trials_csv = outdir / "trials.csv"
    fieldnames = [
                     "trial_id",
                     "score",
                     "alpha_vs_buyhold",
                     "penalty",
                     "ok",
                     "reason",
                     "profit",
                     "profit_per_trade",
                     "trade_count",
                     "max_drawdown",
                     "buy_hold_profit",
                     "trial_config_xlsx",
                     "eval_dir",
    ] + [p.name for p in space.params]

    best_score = float("-inf")
    best_trial_xlsx: Optional[Path] = None

    with trials_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()

        for sample in sampler.iter_trials(space, trials):
            tid = sample.trial_id

            trial_config_xlsx = trials_dir / f"trial_{tid:04d}.xlsx"
            eval_dir = eval_dir_root / f"trial_{tid:04d}"
            eval_dir.mkdir(parents=True, exist_ok=True)

            # write trial config (ONLY TUNING)
            write_trial_config(
                base_config_path=config_strategy,
                out_config_path=trial_config_xlsx,
                params=sample.params,
            )

            # evaluate
            ev = evaluator.evaluate(
                input_csv=input_csv,
                config_strategy=trial_config_xlsx,
                timeframe=timeframe,
                outdir=eval_dir,
                timeout_sec=timeout_sec,
            )

            # objective
            obj = compute_objective(ev.metrics, obj_spec)

            display_best = max(best_score, obj.score) if best_score != float("-inf") else obj.score
            label = f"[{trial_label}] " if trial_label else ""
            print(
                f"\r{label}Trial {tid}/{trials}  score={obj.score:.2f}  best={display_best:.2f}",
                end="",
                flush=True,
            )

            row: Dict[str, Any] = {
                "trial_id": tid,
                "score": obj.score,
                "alpha_vs_buyhold": obj.alpha_vs_buyhold,
                "penalty": obj.penalty,
                "ok": obj.ok,
                "reason": obj.reason if ev.ok else (ev.error or obj.reason),
                "profit": ev.metrics.profit,
                "profit_per_trade": ev.metrics.profit_per_trade,
                "trade_count": ev.metrics.trade_count,
                "max_drawdown": ev.metrics.max_drawdown,
                "buy_hold_profit": ev.metrics.buy_hold_profit,
                "trial_config_xlsx": str(trial_config_xlsx),
                "eval_dir": str(eval_dir),
            }
            # params
            for k, v in sample.params.items():
                row[k] = v

            row_eu = {k: _fmt_eu_num(v) for k, v in row.items()}
            w.writerow(row_eu)

            if obj.score > best_score:
                best_score = obj.score
                best_trial_xlsx = trial_config_xlsx
    print()

    # save best.xlsx
    if best_trial_xlsx is not None:
        best_path = outdir / "best.xlsx"
        best_path.write_bytes(best_trial_xlsx.read_bytes())

        # normalize candidate_values and EU decimals
        try:
            _normalize_best_xlsx(best_path)
        except Exception:
            pass

    return outdir

def run_autotune_regimes_v1(
    *,
    input_csv: Path,
    config_strategy: Path,
    timeframe: str,
    regimes: Optional[Iterable[str]] = None,
    trials: int = 50,
    seed: int = 42,
    train_ratio: float = 0.7,
    outdir: Optional[Path] = None,
    n_min_trades: int = 5,
    timeout_sec: int = 300,
    interactive_selection: bool = False,

) -> Path:
    input_csv = Path(input_csv)
    config_strategy = Path(config_strategy)

    if outdir is None:
        outdir = default_outdir(config_strategy)

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    per_regime_dir = outdir / "per_regime"
    selection_dir = outdir / "selection"
    final_report_dir = outdir / "final_report"
    per_regime_dir.mkdir(exist_ok=True)
    selection_dir.mkdir(exist_ok=True)
    final_report_dir.mkdir(exist_ok=True)

    detected_groups = detect_entry_groups(config_strategy)

    if regimes:
        requested = [str(x).strip() for x in regimes if str(x).strip()]
        target_groups = [g for g in detected_groups if g in requested]
    else:
        target_groups = list(detected_groups)

    runspec = {
        "input_csv": str(input_csv),
        "config_strategy": str(config_strategy),
        "timeframe": timeframe,
        "trials_per_regime": int(trials),
        "seed": int(seed),
        "train_ratio": float(train_ratio),
        "outdir": str(outdir),
        "n_min_trades": int(n_min_trades),
        "detected_entry_groups": detected_groups,
        "target_groups": target_groups,
    }
    (outdir / "runspec_regimes.json").write_text(
        json.dumps(runspec, indent=2),
        encoding="utf-8",
    )

    summary_rows: List[Dict[str, Any]] = []
    tuned_blocks: Dict[str, RegimeBlock] = {}

    for i, group_name in enumerate(target_groups, start=1):
        safe_group = _safe_group_dirname(group_name)
        regime_dir = per_regime_dir / f"regime_{safe_group}"
        regime_dir.mkdir(parents=True, exist_ok=True)

        masked_base = regime_dir / "masked_base.xlsx"
        _write_masked_conditions_config(
            base_config_path=config_strategy,
            out_config_path=masked_base,
            active_entry_group=group_name,
        )

        regime_seed = int(seed) + i - 1
        run_outdir = run_autotune_v1(
            input_csv=input_csv,
            config_strategy=masked_base,
            timeframe=timeframe,
            trials=int(trials),
            seed=regime_seed,
            outdir=regime_dir,
            n_min_trades=int(n_min_trades),
            timeout_sec=int(timeout_sec),
            active_group=group_name,
            trial_label=group_name,
        )

        trials_csv = run_outdir / "trials.csv"
        best_xlsx = run_outdir / "best.xlsx"

        best_profit = None
        best_trades = None
        best_alpha = None
        best_dd = None
        best_score = None

        try:
            df = pd.read_csv(trials_csv, sep=";")

            if len(df) > 0:
                # Convert EU-decimal numeric columns before sorting/selecting best
                for col in [
                    "score",
                    "profit",
                    "trade_count",
                    "alpha_vs_buyhold",
                    "max_drawdown",
                    "buy_hold_profit",
                    "profit_per_trade",
                    "penalty",
                ]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(
                            df[col].astype(str).str.replace(",", ".", regex=False),
                            errors="coerce",
                        )

                df_sorted = df.sort_values("score", ascending=False, na_position="last")
                best = df_sorted.iloc[0]


                best_profit = best.get("profit")
                best_trades = best.get("trade_count")
                best_alpha = best.get("alpha_vs_buyhold")
                best_dd = best.get("max_drawdown")
                best_score = best.get("score")


        except Exception:
            pass

        decision_hint = _decision_hint(
            trade_count=best_trades,
            alpha_vs_buyhold=best_alpha,
            n_min_trades=int(n_min_trades),
        )

        # Candidate block for forward selection/composition
        try:
            if best_xlsx.exists():
                tuned_blocks[group_name] = RegimeBlock(
                    regime=group_name,
                    best_xlsx=best_xlsx,
                    profit_trades=float(best_profit) if best_profit is not None and pd.notna(best_profit) else float("nan"),
                    profit_buyhold=(
                        float(best_profit) - float(best_alpha)
                        if best_profit is not None and best_alpha is not None and pd.notna(best_profit) and pd.notna(best_alpha)
                        else float("nan")
                    ),
                    alpha_regime=float(best_alpha) if best_alpha is not None and pd.notna(best_alpha) else float("nan"),
                    n_trades=int(best_trades) if best_trades is not None and pd.notna(best_trades) else 0,
                    max_dd=float(best_dd) if best_dd is not None and pd.notna(best_dd) else float("nan"),
                )
        except Exception:
            # Keep per-regime autotune robust even if selection metadata cannot be built
            pass

        summary_rows.append(
            {
                "group": group_name,
                "profit": best_profit,
                "trade_count": best_trades,
                "alpha_vs_buyhold": best_alpha,
                "max_drawdown": best_dd,
                "score": best_score,
                "standalone_hint": decision_hint,
                "best_xlsx": str(best_xlsx),
            }
        )

    # ------------------------------------------------------------
    # Regime forward selection / composition
    # ------------------------------------------------------------
    selection_result = None
    try:
        candidate_regimes = [g for g in target_groups if g in tuned_blocks]

        if candidate_regimes:
            fs_spec = ForwardSelectionSpec(
                candidate_regimes=candidate_regimes,
                eps_alpha=0.0,
                dd_tolerance_ratio=0.25,
                n_trades_min=int(n_min_trades),
                interactive=bool(interactive_selection),
                auto_accept=False,
                enforce_constraints=True,
                max_regimes=len(candidate_regimes),
            )

            def _forward_evaluator(
                input_csv: Path,
                config_strategy: Path,
                timeframe: str,
                outdir: Path,
            ) -> EvalResult:
                evaluator = StrategyEvaluator()
                ev = evaluator.evaluate(
                    input_csv=input_csv,
                    config_strategy=config_strategy,
                    timeframe=timeframe,
                    outdir=outdir,
                    timeout_sec=int(timeout_sec),
                )

                obj_spec = ObjectiveSpec(
                    n_min_trades=int(n_min_trades),
                    drawdown_weight=0.5,
                )
                obj = compute_objective(ev.metrics, obj_spec)

                alpha_val = (
                    float(ev.metrics.alpha_vs_buyhold)
                    if ev.metrics.alpha_vs_buyhold is not None
                    else float("nan")
                )
                trades_val = (
                    int(ev.metrics.trade_count)
                    if ev.metrics.trade_count is not None
                    else 0
                )
                dd_val = (
                    float(ev.metrics.max_drawdown)
                    if ev.metrics.max_drawdown is not None
                    else float("nan")
                )
                buy_hold_val = (
                    float(ev.metrics.buy_hold_profit)
                    if getattr(ev.metrics, "buy_hold_profit", None) is not None
                    else float("nan")
                )
                profit_val = (
                    float(ev.metrics.profit)
                    if getattr(ev.metrics, "profit", None) is not None
                    else float("nan")
                )
                penalty_val = (
                    float(obj.penalty)
                    if getattr(obj, "penalty", None) is not None
                    else 0.0
                )

                return EvalResult(
                    ok=bool(ev.ok),
                    score=float(obj.score),
                    alpha=alpha_val,
                    n_trades_closed=trades_val,
                    max_dd=dd_val,
                    penalty=penalty_val,
                    buy_hold_filo=buy_hold_val,
                    net_profit_strat=profit_val,
                    extras={},
                )

            def _forward_builder(
                    base_xlsx: Path,
                    selected_blocks: List[RegimeBlock],
                    out_xlsx: Path,
            ) -> None:

                out_xlsx = Path(out_xlsx)
                out_xlsx.parent.mkdir(parents=True, exist_ok=True)

                # Baseline vera S = {}
                if len(selected_blocks) == 0:
                    _write_forward_baseline_config(
                        base_config_path=base_xlsx,
                        out_config_path=out_xlsx,
                    )
                    return

                active_groups: List[str] = []
                seen = set()

                for block in selected_blocks:
                    regime_name = str(getattr(block, "regime", "") or "").strip()
                    if not regime_name:
                        continue
                    regime_up = regime_name.upper()
                    if regime_up in seen:
                        continue
                    seen.add(regime_up)
                    active_groups.append(regime_name)

                # Step 1: compose CONDITIONS from external template
                _write_forward_composed_conditions_config(
                    base_config_path=base_xlsx,
                    out_config_path=out_xlsx,
                    active_groups=active_groups,
                )

                # Step 2: merge TUNING from selected per-regime best.xlsx files
                _merge_forward_tuning_from_blocks(
                    base_config_path=base_xlsx,
                    selected_blocks=selected_blocks,
                    out_config_path=out_xlsx,
                )
            def _forward_trade_reporter(eval_dir: Path, regime: str) -> None:
                return None

            selection_result = run_regime_forward_selection(
                input_csv=input_csv,
                timeframe=timeframe,
                base_config_xlsx=config_strategy,
                tuned_blocks=tuned_blocks,
                outdir=outdir,
                spec=fs_spec,
                evaluator=_forward_evaluator,
                builder=_forward_builder,
                trade_reporter=_forward_trade_reporter,
                seed=int(seed),
            )
    except Exception as e:
        (selection_dir / "selection_error.txt").write_text(str(e), encoding="utf-8")

    # Legacy per-regime summary (not the composed final report)
    summary_csv = outdir / "per_regime_summary.csv"
    fieldnames = [
        "group",
        "profit",
        "trade_count",
        "alpha_vs_buyhold",
        "max_drawdown",
        "score",
        "standalone_hint",
        "best_xlsx",
    ]

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()
        for row in summary_rows:
            w.writerow({k: _fmt_eu_num(v) for k, v in row.items()})

    # final console summary
    try:
        df_summary = pd.DataFrame(summary_rows)

        if not df_summary.empty:

            if "score" in df_summary.columns:
                df_summary = df_summary.sort_values(by="score", ascending=False, na_position="last")

            printable_cols = [
                c for c in [
                    "group",
                    "profit",
                    "trade_count",
                    "alpha_vs_buyhold",
                    "max_drawdown",
                    "score",
                    "standalone_hint",
                ]
                if c in df_summary.columns
            ]

            df_print = df_summary[printable_cols].copy()

            for col in ["profit", "alpha_vs_buyhold", "max_drawdown", "score"]:
                if col in df_print.columns:
                    df_print[col] = df_print[col].map(_fmt_eu_num)

            print("\n=== REGIME SUMMARY ===")
            print(df_print.to_string(index=False))
            print(f"\nSaved: {summary_csv}")
    except Exception as e:
        print(f"\n[WARN] Could not print regime summary table: {e}")

    return outdir