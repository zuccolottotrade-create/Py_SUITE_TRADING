# Py_SUITE_TRADING/shared/regime_auto_calibration/engine.py
from __future__ import annotations

import csv
import importlib
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Any, Optional, Tuple

import pandas as pd
import csv as _csv

from .score import score_from_metrics
from .parse_report import parse_regime_report_csv, extract_inputs_for_objective
from .regime_objectives import OBJECTIVES
# --- reuse report writer from Strategy Creator (regime_filter_report) ---
try:
    from regime_filter_report.report import build_regime_report
    from regime_filter_report.io_utils import write_single_csv_report
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    _ROOT = Path(__file__).resolve().parents[2]  # Py_SUITE_TRADING/
    _SC_SRC = _ROOT / "5. Strategy Creator" / "strategy_creator" / "src"
    if _SC_SRC.exists() and str(_SC_SRC) not in sys.path:
        sys.path.insert(0, str(_SC_SRC))

    from regime_filter_report.report import build_regime_report
    from regime_filter_report.io_utils import write_single_csv_report

@dataclass(frozen=True)
class TrialResult:
    trial_id: int
    params: Dict[str, float]
    report_csv: Path
    metrics: Dict[str, float]
    score: float


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dirs(py_suite_root: Path) -> Tuple[Path, Path]:
    cfg_dir = py_suite_root / "_data" / "config_filtro_regime"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = py_suite_root / "_data" / "regime_calibration_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir, runs_dir


def _py_suite_root_from_here() -> Path:
    # shared/regime_auto_calibration/engine.py -> shared -> Py_SUITE_TRADING
    return Path(__file__).resolve().parents[2]


def _make_candidate_path(cfg_dir: Path, base_config_csv: Path) -> Path:
    stem = base_config_csv.stem
    if not stem.endswith("_candidate"):
        stem = f"{stem}_candidate"
    return cfg_dir / f"{stem}.csv"


def _make_calibrated_path(cfg_dir: Path, base_config_csv: Path) -> Path:
    stem = base_config_csv.stem
    # richiesto: suffisso _calibrated
    if not stem.endswith("_calibrated"):
        stem = f"{stem}_calibrated"
    return cfg_dir / f"{stem}.csv"


def _write_config_from_base(base_config_csv: Path, out_csv: Path, params: dict) -> None:
    """
    Scrive un config CSV candidato partendo dal base_config_csv, sostituendo i parametri presenti in `params`.

    Supporta CSV con separatore ',' o ';' (tipico EU) e header con spazi tipo: "param; value ;note".
    Schema minimo richiesto: (key|param) + value. Colonna note opzionale.
    """
    import csv

    def _fmt_value_eu(v) -> str:
        """
        Serializza un valore per CSV config in formato EU:
        - niente separatori migliaia
        - virgola decimale
        - precisione stabile
        """
        # stringhe: prova a interpretare come numero (EU o US) e normalizza in EU
        if isinstance(v, str):
            s0 = v.strip()
            if s0 == "":
                return s0

            # tenta parse numerico robusto:
            # - rimuove spazi
            # - gestisce migliaia (.) e decimale (,)
            # - gestisce anche formato US con decimale (.)
            s = s0.replace(" ", "")

            # Caso EU: "1.234,56" -> "1234.56"
            if "," in s:
                s_num = s.replace(".", "").replace(",", ".")
            else:
                # Caso US: "1234.56" -> "1234.56" (nessuna migliaia gestita qui per default)
                s_num = s

            try:
                fv = float(s_num)
                # se parse ok -> serializza in EU usando la stessa logica float
                if abs(fv - round(fv)) < 1e-12:
                    return str(int(round(fv)))
                return format(fv, ".15g").replace(".", ",")
            except Exception:
                # non numerico -> lascia invariato
                return s0

        # bool/int
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, int):
            return str(v)

        # float / numpy scalar
        try:
            fv = float(v)
        except Exception:
            return str(v)

        # se è praticamente un intero, scrivi intero
        if abs(fv - round(fv)) < 1e-12:
            return str(int(round(fv)))

        # significativo, senza migliaia
        s = format(fv, ".15g")  # es. 30.985669961447
        # EU: virgola decimale
        return s.replace(".", ",")

    base_config_csv = Path(base_config_csv)
    out_csv = Path(out_csv)

    # --- detect delimiter (EU ';' vs ',') ---
    with base_config_csv.open("r", encoding="utf-8-sig", newline="") as f:
        first_line = f.readline()

    # Heuristica semplice e stabile: se c'è ';' ed è dominante rispetto a ','
    delim = ";"
    if first_line.count(",") > first_line.count(";"):
        delim = ","

    # --- read base ---
    rows = []
    with base_config_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim, skipinitialspace=True)

        if not reader.fieldnames:
            raise ValueError(f"Config vuoto o header mancante: {base_config_csv}")

        # normalizza header: strip + lowercase
        fieldnames_norm = [h.strip().lower() for h in reader.fieldnames if h is not None]



        # Se ancora arriva una singola colonna contenente ';' (file “rotto” o delimitatore non coerente),
        # proviamo fallback split header.
        if len(fieldnames_norm) == 1 and ";" in fieldnames_norm[0]:
            # esempio: "param; value ;note"
            fieldnames_norm = [x.strip().lower() for x in fieldnames_norm[0].split(";")]



        # --- mapping colonne robusto ---
        col_key = None
        for candidate in ("key", "param", "param_name"):
            if candidate in fieldnames_norm:
                col_key = candidate
                break

        col_value = None
        for candidate in ("value", "val"):
            if candidate in fieldnames_norm:
                col_value = candidate
                break

        if not col_key or not col_value:
            raise ValueError(
                f"Schema config non riconosciuto. "
                f"Trovate colonne: {reader.fieldnames} "
                f"(attese key/param/param_name + value/val)"
            )

        # Per leggere righe anche se header aveva spazi, ricreiamo un reader “canonico”
        # riallineando le chiavi con gli header originali strip/lower.
        # Costruiamo una mappa: header_originale -> header_norm
        hdr_map = {orig: (orig.strip().lower() if orig is not None else orig) for orig in reader.fieldnames}

        for r in reader:
            rr = {}
            for k, v in r.items():
                kn = hdr_map.get(k, k)
                if isinstance(kn, str):
                    kn = kn.strip().lower()
                rr[kn] = v
            rows.append(rr)

    # --- apply overrides ---
    # sostituiamo solo parametri presenti nel base
    for r in rows:
        k = (r.get("key") if "key" in r else r.get("param"))
        if k is None:
            continue
        k2 = str(k).strip()
        if k2 in params:
            r["value"] = _fmt_value_eu(params[k2])

    # --- write out with ';' (EU) per coerenza col base se base era ';' ---
    out_delim = delim
    # Scriviamo sempre con header standard: param,value,note se nel base c'era param
    # oppure key,value,note se nel base c'era key
    out_key_col = "key" if any(("key" in x) for x in rows) and not any(("param" in x) for x in rows) else "param"

    # decide note
    has_note = any(("note" in r) for r in rows)
    out_fields = [out_key_col, "value"] + (["note"] if has_note else [])

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, delimiter=out_delim)
        writer.writeheader()
        for r in rows:
            out_row = {
                out_key_col: (r.get(out_key_col) or r.get("key") or r.get("param")),
                "value": r.get("value", ""),
            }
            if has_note:
                out_row["note"] = r.get("note", "")
            writer.writerow(out_row)


def _default_search_space() -> Dict[str, Tuple[float, float]]:
    """
    TODO: qui definisci range plausibili.
    v1: range larghi, poi li stringiamo.
    Keys devono matchare le 'key' nel CSV config.
    """
    return {
        "adx_trend_enter": (15.0, 40.0),
        "adx_trend_exit":  (10.0, 35.0),
        "adx_range_enter": (15.0, 45.0),
        "adx_range_exit":  (10.0, 40.0),
        "atr_volatile_enter": (0.10, 0.40),
        "atr_volatile_exit":  (0.08, 0.35),
        "atr_range_enter": (0.05, 0.25),
        "atr_range_exit":  (0.04, 0.22),
        "bb_width_range_enter": (0.01, 0.20),
        "bb_width_range_exit":  (0.01, 0.20),
        # --- extra params (presenti in base-config ma mancanti nei trials) ---
        "bb_k": (1.5, 3.5),  # moltiplicatore BB (float)
        "bb_period": (10.0, 40.0),  # periodo BB (int, campionato come float ma poi cast)
        "confirm_bars_trend": (1.0, 8.0),  # int
        "confirm_bars_range": (1.0, 8.0),  # int
        "confirm_bars_volatile": (1.0, 8.0)  # int
    }

def _infer_search_space_from_df(df: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    """
    Build a plausible search space from the input dataset (df0) using quantiles.
    This avoids hard-coded ranges that may be off-scale across timeframes/files.
    """
    import numpy as np

    def _first_existing(cols):
        for c in cols:
            if c in df.columns:
                return c
        return None

    # Candidate column names (robust across naming variants)
    atr_col = _first_existing(["KPI_ATR_PCT_14", "ATR_PCT_14", "KPI_ATR_PCT_10", "ATR_PCT_10"])
    bbw_col = _first_existing(["KPI_BB_WIDTH_20_2p0", "BB_WIDTH_20_2p0", "KPI_BB_WIDTH_20_2p0_PCT", "BB_WIDTH_PCT"])
    adx_col = _first_existing(["KPI_ADX_14", "ADX_14"])

    # Start from defaults (safe fallback)
    space = _default_search_space()

    # ATR_PCT bounds from data
    if atr_col:
        s = pd.to_numeric(df[atr_col], errors="coerce").dropna()
        if len(s) >= 50:
            q50 = float(s.quantile(0.50))
            q80 = float(s.quantile(0.80))
            q90 = float(s.quantile(0.90))
            q95 = float(s.quantile(0.95))
            q99 = float(s.quantile(0.99))

            # volatile thresholds around upper tail
            space["atr_volatile_enter"] = (max(0.0, q80), max(0.0, q99))
            space["atr_volatile_exit"]  = (max(0.0, q50), max(0.0, q95))

            # range thresholds around mid-high
            space["atr_range_enter"] = (max(0.0, q50), max(0.0, q95))
            space["atr_range_exit"]  = (max(0.0, q50 * 0.8), max(0.0, q90))

    # BB width bounds from data
    if bbw_col:
        s = pd.to_numeric(df[bbw_col], errors="coerce").dropna()
        if len(s) >= 50:
            q50 = float(s.quantile(0.50))
            q80 = float(s.quantile(0.80))
            q95 = float(s.quantile(0.95))
            q99 = float(s.quantile(0.99))
            space["bb_width_range_enter"] = (max(0.0, q80), max(0.0, q99))
            space["bb_width_range_exit"] = (max(0.0, q50), max(0.0, q95))

    # ADX bounds from data (optional)
    if adx_col:
        s = pd.to_numeric(df[adx_col], errors="coerce").dropna()
        if len(s) >= 50:
            q40 = float(s.quantile(0.40))
            q60 = float(s.quantile(0.60))
            q75 = float(s.quantile(0.75))
            q90 = float(s.quantile(0.90))
            space["adx_trend_enter"] = (max(5.0, q60), max(10.0, q90))
            space["adx_trend_exit"]  = (max(5.0, q40), max(10.0, q75))
            space["adx_range_enter"] = (max(5.0, q60), max(10.0, q90))
            space["adx_range_exit"]  = (max(5.0, q40), max(10.0, q75))

    return space


def _sample_params(rng: random.Random, space: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
    p = {}
    for k, (lo, hi) in space.items():
        p[k] = lo + (hi - lo) * rng.random()

    # --- cast parametri interi (periodi / confirm bars) ---
    int_params = {
        "bb_period",
        "confirm_bars_trend",
        "confirm_bars_range",
        "confirm_bars_volatile",
    }
    for k in int_params:
        if k in p:
            p[k] = int(round(p[k]))
            if p[k] < 1:
                p[k] = 1

    # vincoli isteresi (enter >= exit)
    for base in ("adx_trend", "adx_range", "atr_volatile", "atr_range", "bbw"):
        ke = f"{base}_enter"
        kx = f"{base}_exit"
        if ke in p and kx in p and p[ke] < p[kx]:
            p[ke], p[kx] = p[kx], p[ke]
    return p

def _load_input_df(input_csv: Path) -> pd.DataFrame:
    """
    Loader robusto:
    - sniff delimiter su un campione iniziale
    - usa engine='python' (più tollerante)
    - fallback su separatori comuni
    - normalizza colonne KPI_* a numerico se dtype=object
    """

    input_csv = Path(input_csv)

    if not input_csv.exists():
        raise SystemExit(
            f"[AUTO_CAL][FATAL] input CSV not found: {input_csv} (cwd={Path().resolve()})"
        )

    if not input_csv.is_file():
        raise SystemExit(
            f"[AUTO_CAL][FATAL] input path is not a file: {input_csv}"
        )

    # 👇 SOLO ORA leggiamo il file
    sample = input_csv.read_text(encoding="utf-8", errors="replace")[:50_000]

    sep = None
    try:
        sep = _csv.Sniffer().sniff(
            sample, delimiters=[",", ";", "\t", "|"]
        ).delimiter
    except Exception:
        sep = None

    seps = [sep, ";", ",", "\t", "|"]
    seen = set()
    seps = [s for s in seps if s and not (s in seen or seen.add(s))]

    last_err = None
    for s in seps:
        try:
            df = pd.read_csv(
                input_csv,
                sep=s,
                engine="python",
                encoding="utf-8",
                encoding_errors="replace",
            )

            # --------------------------------------------------
            # 🔧 NORMALIZZAZIONE KPI NUMERICI
            # --------------------------------------------------
            # Se una colonna KPI_* è dtype object (stringhe miste),
            # la convertiamo a numerico in modo sicuro.
            # Questo evita che il regime classifier collassi in UNKNOWN.
            kpi_cols = [c for c in df.columns if c.startswith("KPI_")]

            for c in kpi_cols:
                if df[c].dtype == "object":
                    df[c] = pd.to_numeric(
                        df[c].astype(str).str.replace(",", ".", regex=False),
                        errors="coerce",
                    )

            return df

        except Exception as e:
            last_err = e

    raise last_err

def _resolve_apply_fn(classifier_module, debug: bool = True):
    """
    Trova la funzione di apply nel modulo classifier in modo robusto.
    Ritorna SEMPRE (fn, name) oppure solleva AttributeError.
    """
    import inspect

    candidates_priority = [
        "apply_regime_L1",
        "apply_regime_l1",
        "apply_regime",
        "apply",
    ]

    if debug:
        print(f"[AUTO_CAL][APPLY][RESOLVER] module={getattr(classifier_module,'__name__','?')}")
        print(f"[AUTO_CAL][APPLY][RESOLVER] file={getattr(classifier_module,'__file__','<no_file>')}")
        print(f"[AUTO_CAL][APPLY][RESOLVER] priority={candidates_priority}")

    # 1) priority
    for name in candidates_priority:
        fn = getattr(classifier_module, name, None)
        if callable(fn):
            if debug:
                try:
                    sig = inspect.signature(fn)
                except Exception:
                    sig = "(signature unavailable)"
                try:
                    src = inspect.getsourcefile(fn) or "<no_sourcefile>"
                except Exception:
                    src = "<no_sourcefile>"
                print(f"[AUTO_CAL][APPLY][RESOLVER] selected (priority) fn={name} sig={sig} src={src}")
            return fn, name

    # 2) fallback: apply_regime* / apply_*
    names = []
    for n in dir(classifier_module):
        if n.startswith("__"):
            continue
        if n.startswith("apply_regime") or n.startswith("apply_"):
            fn = getattr(classifier_module, n, None)
            if callable(fn):
                names.append(n)

    names = sorted(set(names), key=lambda x: (len(x), x))

    if debug:
        print(f"[AUTO_CAL][APPLY][RESOLVER] fallback_candidates={names}")

    if names:
        chosen = names[0]
        fn = getattr(classifier_module, chosen, None)
        if callable(fn):
            if debug:
                try:
                    sig = inspect.signature(fn)
                except Exception:
                    sig = "(signature unavailable)"
                try:
                    src = inspect.getsourcefile(fn) or "<no_sourcefile>"
                except Exception:
                    src = "<no_sourcefile>"
                print(f"[AUTO_CAL][APPLY][RESOLVER] selected (fallback) fn={chosen} sig={sig} src={src}")
            return fn, chosen

    # 3) raise (MAI None)
    apply_like = [n for n in dir(classifier_module) if "apply" in n.lower() and not n.startswith("__")]
    raise AttributeError(
        "Classifier module non espone funzioni applicabili. "
        f"Attese: {candidates_priority} o callable 'apply_regime*' / 'apply_*'. "
        f"Trovate: {apply_like}"
    )

    import inspect
    from pathlib import Path

    def _resolve_apply_fn_from_classifier(classifier_module, candidates_priority, debug: bool = True):

        if debug:
            mod_name = getattr(classifier_module, "__name__", "?")
            mod_file = getattr(classifier_module, "__file__", "<no_file>")
            print(f"[AUTO_CAL][APPLY][RESOLVER] module={mod_name}")
            print(f"[AUTO_CAL][APPLY][RESOLVER] file={mod_file}")

        # --------------------------------------------------
        # 1) PRIORITY LIST
        # --------------------------------------------------
        for name in candidates_priority:
            fn = getattr(classifier_module, name, None)
            if callable(fn):
                if debug:
                    try:
                        sig = inspect.signature(fn)
                    except Exception:
                        sig = "(signature unavailable)"
                    try:
                        src = inspect.getsourcefile(fn) or "<no_sourcefile>"
                    except Exception:
                        src = "<no_sourcefile>"

                    print(f"[AUTO_CAL][APPLY][RESOLVER] selected (priority) fn={name}")
                    print(f"[AUTO_CAL][APPLY][RESOLVER] signature={sig}")
                    print(f"[AUTO_CAL][APPLY][RESOLVER] source={src}")

                return fn, name

        # --------------------------------------------------
        # 2) FALLBACK: cerca qualunque callable con prefisso apply*
        # --------------------------------------------------
        names = []
        for n in dir(classifier_module):

            if n.startswith("__"):
                continue

            if n.startswith("apply_regime") or n.startswith("apply_"):
                fn = getattr(classifier_module, n, None)
                if callable(fn):
                    names.append(n)

        names = sorted(set(names), key=lambda x: (len(x), x))

        if debug:
            print(f"[AUTO_CAL][APPLY][RESOLVER] fallback candidates={names}")

        if names:
            chosen = names[0]
            fn = getattr(classifier_module, chosen, None)

            if callable(fn):
                if debug:
                    try:
                        sig = inspect.signature(fn)
                    except Exception:
                        sig = "(signature unavailable)"
                    try:
                        src = inspect.getsourcefile(fn) or "<no_sourcefile>"
                    except Exception:
                        src = "<no_sourcefile>"

                    print(f"[AUTO_CAL][APPLY][RESOLVER] selected (fallback) fn={chosen}")
                    print(f"[AUTO_CAL][APPLY][RESOLVER] signature={sig}")
                    print(f"[AUTO_CAL][APPLY][RESOLVER] source={src}")

                return fn, chosen

        # --------------------------------------------------
        # 3) ERRORE DIAGNOSTICO
        # --------------------------------------------------
        apply_like = [
            n for n in dir(classifier_module)
            if "apply" in n.lower() and not n.startswith("__")
        ]

        raise AttributeError(
            "Classifier module non espone funzioni applicabili.\n"
            f"Attese (priority): {candidates_priority}\n"
            f"Fallback 'apply*' trovate: {apply_like}"
        )

def _resolve_params_from_spec_module(
    spec_module,
    candidate_cfg: Optional[Path] = None,
    base_config_csv: Optional[Path] = None,
    debug_cfg: bool = False,
):
    """
    Trova e invoca una funzione che restituisce i params per REGIME_L1 dal modulo specifico.

    Supporta più naming pattern (per compatibilità con versioni diverse):
    - resolve_regime_l1_params
    - resolve_regime_L1_params
    - resolve_params
    - get_params / get_regime_params
    - load_filter_defaults_from_csv (se esposta)
    """
    import inspect

    candidate_names = [
        "resolve_regime_l1_params",
        "resolve_regime_L1_params",
        "resolve_regime_params",
        "resolve_params",
        "get_regime_l1_params",
        "get_regime_params",
        "get_params",
        "_load_filter_defaults_from_csv",
        "load_filter_defaults_from_csv",
    ]

    from pathlib import Path
    import inspect

    if debug_cfg:
        mod_file = getattr(spec_module, "__file__", "<no_file>")
        print(f"[AUTO_CAL][PARAMS][RESOLVER] spec_module={getattr(spec_module, '__name__', '?')} file={mod_file}")
        if candidate_cfg is not None:
            print(f"[AUTO_CAL][PARAMS][RESOLVER] candidate_cfg={Path(candidate_cfg).resolve()}")
        if base_config_csv is not None:
            print(f"[AUTO_CAL][PARAMS][RESOLVER] base_config_csv={Path(base_config_csv).resolve()}")

    # mapping nomi argomento possibili per passare il path config
    cfg_arg_candidates = ["config_csv", "config_path", "cfg_path", "csv_path", "path"]

    for name in candidate_names:
        fn = getattr(spec_module, name, None)
        if not callable(fn):
            continue

        try:
            sig = inspect.signature(fn)
            params_list = list(sig.parameters.values())

            # params "required" (positional-only o positional-or-keyword senza default)
            required = [
                p for p in params_list
                if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]

            if debug_cfg:
                try:
                    src = inspect.getsourcefile(fn) or "<no_sourcefile>"
                except Exception:
                    src = "<no_sourcefile>"
                print(f"[AUTO_CAL][PARAMS][RESOLVER] try_fn={name} src={src} sig={sig}")

            out = None

            # 1) Se ho candidate_cfg, provo a passarlo se la signature lo consente
            if candidate_cfg is not None:
                accepted = set(sig.parameters.keys())

                passed = False
                # (a) keyword arg tipo config_csv/config_path/...
                for an in cfg_arg_candidates:
                    if an in accepted:
                        out = fn(**{an: str(candidate_cfg)})
                        passed = True
                        if debug_cfg:
                            print(f"[AUTO_CAL][PARAMS][RESOLVER] used_fn={name} passed {an}={candidate_cfg}")
                        break

                # (b) positional singolo argomento
                if not passed and len(required) == 1:
                    out = fn(str(candidate_cfg))
                    passed = True
                    if debug_cfg:
                        print(f"[AUTO_CAL][PARAMS][RESOLVER] used_fn={name} passed positional={candidate_cfg}")

                # (c) fallback: nessun modo di passare cfg → chiamata senza args (ma warning)
                if not passed:
                    if len(required) == 0:
                        out = fn()
                        if debug_cfg:
                            print(
                                f"[AUTO_CAL][PARAMS][RESOLVER][WARN] used_fn={name} cannot accept cfg; called with no args")
                    else:
                        # non posso chiamarla: richiede args che non so fornire
                        if debug_cfg:
                            print(
                                f"[AUTO_CAL][PARAMS][RESOLVER][SKIP] fn={name} requires args={required} and no cfg mapping found")
                        continue

            # 2) Se candidate_cfg è None, mantengo vecchio comportamento: callable senza args
            else:
                if len(required) == 0:
                    out = fn()
                    if debug_cfg:
                        print(f"[AUTO_CAL][PARAMS][RESOLVER] used_fn={name} called with no args (candidate_cfg=None)")
                else:
                    continue

            # validate output
            if isinstance(out, dict) and len(out) > 0:
                if debug_cfg:
                    try:
                        kk = sorted(out.keys())
                        print(f"[AUTO_CAL][PARAMS][RESOLVER] ok fn={name} keys={kk}")
                    except Exception:
                        print(f"[AUTO_CAL][PARAMS][RESOLVER] ok fn={name} (dict)")
                return out, name

        except Exception as e:
            # se signature non ispezionabile o call fallisce, prova prossimo (ma logga)
            if debug_cfg:
                print(f"[AUTO_CAL][PARAMS][RESOLVER][ERR] fn={name} -> {type(e).__name__}: {e}")
            continue

    # Fallback: cerca qualunque callable che contenga 'resolve' e 'param'
    hits = []
    for n in dir(spec_module):
        nl = n.lower()
        if "resolve" in nl and "param" in nl:
            fn = getattr(spec_module, n, None)
            if callable(fn):
                hits.append(n)

    hits = sorted(hits)
    if hits:
        fn = getattr(spec_module, hits[0])
        try:
            out = fn()
            if isinstance(out, dict) and len(out) > 0:
                return out, hits[0]
        except Exception:
            pass

    raise AttributeError(
        "Modulo specifico non espone un resolver params riconosciuto. "
        f"Attesi uno tra: {candidate_names}. "
        f"Trovati metodi 'resolve*param*': {hits}"
    )

def _params_from_config_csv(cfg_csv: Path) -> dict:
    """
    Legge un config CSV (schema param/value[/note]) e ritorna dict {param: float|str}.

    Supporta separatore ',' o ';' e header con spazi.
    """
    import csv
    from pathlib import Path

    cfg_csv = Path(cfg_csv)

    with cfg_csv.open("r", encoding="utf-8-sig", newline="") as f:
        first_line = f.readline()

    delim = ";"
    if first_line.count(",") > first_line.count(";"):
        delim = ","

    out = {}
    with cfg_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim, skipinitialspace=True)
        if not reader.fieldnames:
            return out

        # normalizza header
        hdrs = [h.strip().lower() for h in reader.fieldnames if h is not None]

        # se header collassato
        if len(hdrs) == 1 and ";" in hdrs[0]:
            hdrs = [x.strip().lower() for x in hdrs[0].split(";")]

        col_key = "key" if "key" in hdrs else ("param" if "param" in hdrs else None)
        col_val = "value" if "value" in hdrs else None
        if col_key is None or col_val is None:
            raise ValueError(f"[AUTO_CAL] schema cfg non riconosciuto in {cfg_csv.name}: {reader.fieldnames}")

        # mappa header originali -> norm
        hdr_map = {orig: (orig.strip().lower() if orig is not None else orig) for orig in reader.fieldnames}

        for r in reader:
            rr = {}
            for k, v in r.items():
                kn = hdr_map.get(k, k)
                if isinstance(kn, str):
                    kn = kn.strip().lower()
                rr[kn] = v

            k = rr.get(col_key)
            v = rr.get(col_val)
            if k is None:
                continue

            k = str(k).strip()
            if k == "":
                continue

            v = "" if v is None else str(v).strip()
            if v == "":
                continue

            # parse numerico se possibile (accetta anche virgola EU)
            v_num = None
            try:
                v2 = v.replace(",", ".")
                v_num = float(v2)
            except Exception:
                v_num = None

            out[k] = v_num if v_num is not None else v

    return out


def _apply_via_core(df: pd.DataFrame, spec_module, candidate_cfg: Path, base_config_csv: Path):
    """
    Fallback apply: applica REGIME_L1 usando il modulo specifico EQQQ (shared.regime_classifier_EQQQ_1d)
    passando i params del trial direttamente come overrides.

    NOTA: Questo bypassa il file-swap e impedisce che vengano ri-letti i valori "base" dal CSV standard.
    """
    import importlib
    import inspect
    from pathlib import Path

    candidate_cfg = Path(candidate_cfg)

    # 1) params direttamente dal CSV candidato
    params = _params_from_config_csv(candidate_cfg)
    if not params:
        raise ValueError(f"[AUTO_CAL] params vuoti letti da candidate_cfg={candidate_cfg}")



    # 2) scegli modulo apply:
    # - se spec_module è valido e ha apply_regime_L1, usalo
    # - altrimenti importa direttamente shared.regime_classifier_EQQQ_1d
    mod = None
    if spec_module is not None and hasattr(spec_module, "apply_regime_L1"):
        mod = spec_module
    else:
        mod = importlib.import_module("shared.regime_classifier_EQQQ_1d")

    fn = getattr(mod, "apply_regime_L1", None)
    if fn is None:
        raise AttributeError(f"[AUTO_CAL] {getattr(mod,'__name__','?')} non espone apply_regime_L1 (atteso).")

    # 3) chiama apply_regime_L1 passando overrides nel canale corretto
    try:
        keys = set(inspect.signature(fn).parameters.keys())
    except Exception:
        keys = set()

    # Preferenza: 'overrides' (è la signature del modulo EQQQ)
    if "overrides" in keys:
        return fn(df, regime_filter="L1", overrides=params)

    # Alternativa compatibile: cfg={"overrides": params} (il tuo apply_regime_L1 bridge lo supporta)
    if "cfg" in keys:
        return fn(df, regime_filter="L1", cfg={"overrides": params})

    # Se esiste un canale esplicito params_override
    if "params_override" in keys:
        return fn(df, regime_filter="L1", params_override=params)

    # Se esiste un canale generico params/config
    if "params" in keys:
        return fn(df, regime_filter="L1", params=params)
    if "config" in keys:
        return fn(df, regime_filter="L1", config=params)

    # Ultima spiaggia: posizionale (df, overrides)
    try:
        return fn(df, params)
    except TypeError:
        return fn(df, "L1", params)




def _apply_regime(
    df: pd.DataFrame,
    classifier_module,
    candidate_cfg: Path,
    base_config_csv: Path,
):
    # -----------------------------
    # Normalize module path
    # -----------------------------
    if classifier_module and "." not in classifier_module:
        classifier_module = f"shared.{classifier_module}"

    print(f"[AUTO_CAL][APPLY] classifier_module = {classifier_module}")
    import pathlib
    print(f"[AUTO_CAL][APPLY] candidate_cfg     = {candidate_cfg} (exists={pathlib.Path(candidate_cfg).exists()})")
    print(f"[AUTO_CAL][APPLY] base_config_csv   = {base_config_csv}")

    assert candidate_cfg is not None, "candidate_cfg is None"
    assert pathlib.Path(candidate_cfg).exists(), f"candidate_cfg missing on disk: {candidate_cfg}"

    """
    Applica il regime classifier al dataframe usando la config candidata.

    - Se apply_regime_L1 accetta cfg_path/cfg_file/config_path/config_file -> passiamo il path.
    - Altrimenti: fallback robusto = sostituiamo temporaneamente il file base_config_csv
      (che il classifier potrebbe leggere internamente), chiamiamo apply_regime_L1(df) senza kwargs,
      e poi ripristiniamo l'originale.
    """
    import inspect
    import shutil
    from pathlib import Path

    candidate_cfg = Path(candidate_cfg)
    base_config_csv = Path(base_config_csv)

    print(f"[AUTO_CAL][APPLY] classifier_module = {classifier_module}")
    print(f"[AUTO_CAL][APPLY] candidate_cfg     = {candidate_cfg}")
    print(f"[AUTO_CAL][APPLY] base_config_csv   = {base_config_csv}")
    print(f"[AUTO_CAL][APPLY] candidate_exists  = {candidate_cfg.exists()}")

    # Se il modulo specifico non espone apply_* (caso regime_classifier_EQQQ_1d),
    # usiamo pipeline standard: resolve params dal modulo specifico + apply via core.

    # -----------------------------
    # Normalize classifier module path (es. "regime_classifier_EQQQ_1d" -> "shared.regime_classifier_EQQQ_1d")
    # -----------------------------
    import importlib

    if isinstance(classifier_module, str) and "." not in classifier_module:
        classifier_module = f"shared.{classifier_module}"

    # assicura modulo importato
    if isinstance(classifier_module, str):
        classifier_module_obj = importlib.import_module(classifier_module)
    else:
        classifier_module_obj = classifier_module

    try:
        fn, fn_name = _resolve_apply_fn(classifier_module_obj)
    except AttributeError:
        print("[AUTO_CAL][APPLY] _resolve_apply_fn: AttributeError -> fallback _apply_via_core")
        return _apply_via_core(df, classifier_module, candidate_cfg, base_config_csv)
    # 1) Tentativi "soft" se la signature supporta keyword
    try:
        sig = inspect.signature(fn)
        params = set(sig.parameters.keys())
        print(f"[AUTO_CAL][APPLY] apply fn={fn_name} signature_params={sorted(params)}")
        # --- SUPPORTO OVERRIDES (EQQQ style) ---
        # Se la funzione accetta "overrides"/"cfg"/"params_override", passiamo i params del trial
        # letti dal CSV candidato. Questo evita il file-swap quando il modulo non legge base_config_csv.
        if ("overrides" in params) or ("cfg" in params) or ("params_override" in params) or ("params" in params) or ("config" in params):
            trial_params = _params_from_config_csv(candidate_cfg)
            if not trial_params:
                raise ValueError(f"[AUTO_CAL][APPLY] params vuoti letti da candidate_cfg={candidate_cfg}")

            # prova canale 'overrides'
            if "overrides" in params:
                print("[AUTO_CAL][APPLY] using overrides kw")
                print(f"[REGIME][CFG_USED] overrides_from={candidate_cfg}")
                return fn(df, regime_filter="L1", overrides=trial_params)

            # prova canale 'cfg'
            if "cfg" in params:
                print("[AUTO_CAL][APPLY] using cfg kw")
                print(f"[REGIME][CFG_USED] cfg(overrides)_from={candidate_cfg}")
                return fn(df, regime_filter="L1", cfg={"overrides": trial_params})

            # altri canali compatibili
            if "params_override" in params:
                print("[AUTO_CAL][APPLY] using params_override kw")
                print(f"[REGIME][CFG_USED] params_override_from={candidate_cfg}")
                return fn(df, regime_filter="L1", params_override=trial_params)

            if "params" in params:
                print("[AUTO_CAL][APPLY] using params kw")
                print(f"[REGIME][CFG_USED] params_from={candidate_cfg}")
                return fn(df, regime_filter="L1", params=trial_params)

            if "config" in params:
                print("[AUTO_CAL][APPLY] using config kw")
                print(f"[REGIME][CFG_USED] config_from={candidate_cfg}")
                return fn(df, regime_filter="L1", config=trial_params)

        if "cfg_path" in params:
            print("[AUTO_CAL][APPLY] using cfg_path kw")
            print(f"[REGIME][CFG_USED] cfg_path={candidate_cfg}")
            return fn(df, cfg_path=str(candidate_cfg))

        if "cfg_file" in params:
            print("[AUTO_CAL][APPLY] using cfg_file kw")
            print(f"[REGIME][CFG_USED] cfg_file={candidate_cfg}")
            return fn(df, cfg_file=str(candidate_cfg))

        if "config_path" in params:
            print("[AUTO_CAL][APPLY] using config_path kw")
            print(f"[REGIME][CFG_USED] config_path={candidate_cfg}")
            return fn(df, config_path=str(candidate_cfg))

        if "config_file" in params:
            print("[AUTO_CAL][APPLY] using config_file kw")
            print(f"[REGIME][CFG_USED] config_file={candidate_cfg}")
            return fn(df, config_file=str(candidate_cfg))

        # se accetta un secondo argomento posizionale (non keyword-only), proviamo:
        # (alcuni moduli usano apply_regime_L1(df, cfg_csv))
        non_kwonly = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if len(non_kwonly) >= 2:
            print("[AUTO_CAL][APPLY] using 2nd positional arg")
            print(f"[REGIME][CFG_USED] positional_cfg={candidate_cfg}")
            return fn(df, str(candidate_cfg))

    except Exception as e:
        # Non blocchiamo qui: passiamo al fallback file-swap
        print(f"[AUTO_CAL][APPLY] signature-based apply failed -> fallback file-swap. err={type(e).__name__}: {e}")

    # 2) Fallback hard: file-swap sul base_config_csv
    if not base_config_csv.exists():
        raise FileNotFoundError(f"base_config_csv non trovato: {base_config_csv}")

    tmp_bak = base_config_csv.with_suffix(base_config_csv.suffix + ".bak_autocal")

    print("[AUTO_CAL][APPLY] using HARD file-swap fallback")
    print(f"[REGIME][CFG_USED] swapping base_config_csv={base_config_csv} <- candidate_cfg={candidate_cfg}")

    # Copia original -> bak, candidate -> base, run, restore
    try:
        if tmp_bak.exists():
            tmp_bak.unlink()

        shutil.copy2(base_config_csv, tmp_bak)
        shutil.copy2(candidate_cfg, base_config_csv)

        # chiamata senza kwargs (signature “chiusa”)
        return fn(df)

    finally:
        # restore best-effort
        try:
            if tmp_bak.exists():
                shutil.copy2(tmp_bak, base_config_csv)
                tmp_bak.unlink()
        except Exception:
            # se fallisce il restore, non blocchiamo qui: verrà visto dai log/risultati
            pass

def _write_report_reusing_existing(
    df_with_regime: pd.DataFrame,
    report_out_csv: Path,
) -> None:
    """
    Reuse writer standard del wizard:
      - build_regime_report(df) costruisce le "sheets"
      - write_single_csv_report(...) scrive il CSV unico con sezioni ### SHEET=...
    """
    report_out_csv.parent.mkdir(parents=True, exist_ok=True)

    # default coerente col tuo stack: colonna regime canonica prodotta da apply_regime_L1
    regime_col = "REGIME_L1"
    if "REGIME_L1" not in df_with_regime.columns:
        # fallback (per varianti)
        for cand in ("REGIME_L1_RAW", "REGIME_L1_CODE", "REGIME_L1_NAME"):
            if cand in df_with_regime.columns:
                regime_col = cand
                break

    # Assicura forward returns per STATS/PRO nel report (r1/r5)
    df_with_regime = _ensure_forward_returns(df_with_regime, close_col="close")
    sheets = build_regime_report(df_with_regime, regime_col=regime_col)

    # NB: la signature la verifichiamo sotto; intanto usiamo l'ordine più probabile
    write_single_csv_report(Path(report_out_csv), sheets)

def _ensure_forward_returns(df: pd.DataFrame, close_col: str = "close") -> pd.DataFrame:
    """Assicura colonne r1 e r5 (forward returns) calcolate da close."""
    out = df
    if close_col not in out.columns:
        return out
    c = pd.to_numeric(out[close_col], errors="coerce")
    if "r1" not in out.columns:
        out["r1"] = (c.shift(-1) / c) - 1.0
    if "r5" not in out.columns:
        out["r5"] = (c.shift(-5) / c) - 1.0
    return out


def _compute_trial_metrics(df: pd.DataFrame, regime_col: str = "REGIME_L1") -> dict:
    """
    Calcola metriche per auto-calibration direttamente dal dataframe già classificato.
    Richiede SciPy per chi2/kruskal (se non disponibile → NaN).
    """
    import numpy as np

    m = {
        "coverage_penalty": np.nan,
        "chi2_pvalue": np.nan,
        "kruskal_r5_pvalue": np.nan,
        "max_abs_cliff_r5": np.nan,
        "spread_r5_mean": np.nan,
    }

    if regime_col not in df.columns:
        return m

    # normalize regime labels
    reg = (
        df[regime_col]
        .astype(str)
        .fillna("")
        .str.strip()
        .str.upper()
    )

    # coverage
    vc = reg.value_counts(dropna=False)
    total = float(vc.sum()) if len(vc) else 0.0
    if total <= 0:
        return m

    # chi2 vs uniform (fallback robusto se non hai target bands in questa fase)
    try:
        from scipy.stats import chisquare
        obs = vc.values.astype(float)
        exp = np.ones_like(obs) * (obs.sum() / len(obs))
        _, p = chisquare(f_obs=obs, f_exp=exp)
        m["chi2_pvalue"] = float(p)
    except Exception:
        pass

    # forward returns
    df2 = df.copy()
    df2[regime_col] = reg.values
    df2 = _ensure_forward_returns(df2, close_col="close")

    # kruskal su r5
    try:
        from scipy.stats import kruskal
        groups = []
        for k in vc.index.tolist():
            x = pd.to_numeric(df2.loc[df2[regime_col] == k, "r5"], errors="coerce").dropna().values
            if len(x) >= 5:
                groups.append(x)
        if len(groups) >= 2:
            _, p = kruskal(*groups)
            m["kruskal_r5_pvalue"] = float(p)
    except Exception:
        pass

    # spread r5 mean
    try:
        means = []
        for k in vc.index.tolist():
            x = pd.to_numeric(df2.loc[df2[regime_col] == k, "r5"], errors="coerce").dropna()
            if len(x):
                means.append(float(x.mean()))
        if len(means) >= 2:
            m["spread_r5_mean"] = float(max(means) - min(means))
    except Exception:
        pass

    # cliff's delta (max abs tra coppie regimi su r5)
    def _cliffs_delta(a, b) -> float:
        # O(n*m) ok su dataset piccolo; se serve ottimizzare, lo facciamo dopo
        a = np.asarray(a)
        b = np.asarray(b)
        gt = 0
        lt = 0
        for x in a:
            gt += int((x > b).sum())
            lt += int((x < b).sum())
        denom = a.size * b.size
        return (gt - lt) / denom if denom else np.nan

    try:
        vals = {}
        for k in vc.index.tolist():
            x = pd.to_numeric(df2.loc[df2[regime_col] == k, "r5"], errors="coerce").dropna().values
            if len(x) >= 5:
                vals[k] = x
        keys = list(vals.keys())
        best = 0.0
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                d = _cliffs_delta(vals[keys[i]], vals[keys[j]])
                if not np.isnan(d):
                    best = max(best, abs(float(d)))
        if len(keys) >= 2:
            m["max_abs_cliff_r5"] = float(best)
    except Exception:
        pass

    # coverage_penalty: per ora 0 (se vuoi bands 1D le aggiungiamo in PATCH 13)
    m["coverage_penalty"] = 0.0
    return m


def _get_default_target_bands(timeframe: str) -> dict:
    """
    Target bands % per auto-calibration.
    Nota: volutamente semplice e indipendente dal wizard.
    Chiavi attese: VOLATILE, TREND, RANGE, LATERAL, UNKNOWN
    (Se nel report hai anche TREND_UP/DOWN, puoi estendere in futuro.)
    """
    tf = (timeframe or "").strip().lower()

    # 1D: VOLATILE può essere 0% (non forziamo la presenza di barre VOLATILE)
    if tf in ("1d", "1day", "day", "daily"):
        return {
            "TREND": (25.0, 45.0),
            "RANGE": (30.0, 55.0),
            "LATERAL": (30.0, 55.0),
            "VOLATILE": (0.0, 20.0),
            "UNKNOWN": (0.0, 0.0),
        }

    # Intraday / default
    return {
        "TREND": (25.0, 45.0),
        "RANGE": (30.0, 55.0),
        "LATERAL": (30.0, 55.0),
        "VOLATILE": (5.0, 20.0),
        "UNKNOWN": (0.0, 0.0),
    }

def run_calibration(
    *,
    input_csv: Path,
    classifier_module: str,
    base_config_csv: Path,
    trials: int,
    seed: int,
    outdir: Optional[Path],
) -> Dict[str, Any]:
    root = _py_suite_root_from_here()
    cfg_dir, runs_dir = _ensure_dirs(root)

    # v0: TS – REGIME_L1 1D tuning => bands fisse 1D (timeframe non passato dal CLI)
    target_bands = _get_default_target_bands("1d")

    run_dir = outdir if outdir else (runs_dir / f"{_ts()}_{base_config_csv.stem}")
    run_dir.mkdir(parents=True, exist_ok=True)

    candidates_dir = run_dir / "candidates"
    best_dir = run_dir / "best"
    candidates_dir.mkdir(exist_ok=True)
    best_dir.mkdir(exist_ok=True)

    rng = random.Random(seed)
    df0 = _load_input_df(input_csv)
    # --- PRECHECK KPI core (se mancano -> classifier tende a UNKNOWN ovunque) ---
    must_have = ["KPI_ADX_14", "KPI_ATR_PCT_14", "KPI_BB_WIDTH_20_2p0"]
    missing = [c for c in must_have if c not in df0.columns]
    if missing:
        print(f"[AUTO_CAL][WARN] KPI mancanti nel CSV input: {missing}")
    else:
        for c in must_have:
            nn = int(df0[c].notna().sum())
            print(f"[AUTO_CAL][KPI] {c}: non-null={nn}/{len(df0)}  min={df0[c].min()} max={df0[c].max()}")



    space = _infer_search_space_from_df(df0)
    print("[AUTO_CAL] inferred search space:", space)

    # --- trials.csv schema (must match keys written in `row`)
    param_cols = sorted(space.keys())
    metric_cols = [
        "coverage_penalty",
        "chi2_pvalue",
        "kruskal_r5_pvalue",
        "max_abs_cliff_r5",
        "spread_r5_mean",
    ]
    obj_cols = ["obj_hard_failed", "obj_J_cov", "obj_J_chi2", "obj_J_kr"]

    fieldnames = ["trial_id", "score", *param_cols, *metric_cols, "report_csv", *obj_cols]


    trials_csv = run_dir / "trials.csv"



    with trials_csv.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")

        wr.writeheader()

        best: Optional[TrialResult] = None

        for t in range(1, trials + 1):
            params = _sample_params(rng, space)

            # candidate config path (globale in _data/config_filtro_regime)
            candidate_cfg = _make_candidate_path(cfg_dir, base_config_csv)
            _write_config_from_base(base_config_csv, candidate_cfg, params)

            print(f"[AUTO_CAL][CFG] base_config_csv      = {base_config_csv}")
            print(f"[AUTO_CAL][CFG] candidate_cfg        = {candidate_cfg}")
            print(f"[AUTO_CAL][CFG] candidate_exists     = {candidate_cfg.exists()}")

            import hashlib

            def _sha1_file(p):
                b = p.read_bytes()
                return hashlib.sha1(b).hexdigest(), len(b)

            # 1) prova params campionati (ordinati, 1 riga)
            try:
                k = sorted(params.keys())
                p_line = ", ".join([f"{kk}={params[kk]}" for kk in k])
            except Exception:
                p_line = str(params)

            print(f"[AUTO_CAL][TRIAL {t:04d}] sampled_params: {p_line}")

            # 2) prova che il candidate_cfg esiste e cambia davvero su disco
            print(f"[AUTO_CAL][CFG] candidate_cfg        = {candidate_cfg.resolve()}")
            print(f"[AUTO_CAL][CFG] candidate_exists     = {candidate_cfg.exists()}")
            if candidate_cfg.exists():
                h, n = _sha1_file(candidate_cfg)
                print(f"[AUTO_CAL][CFG] candidate_sha1       = {h} bytes={n}")
            else:
                print(f"[AUTO_CAL][CFG][ERR] candidate_cfg missing after write!")

            # hard assert: NON deve mai usare base_config qui
            assert candidate_cfg.exists(), f"candidate_cfg does not exist: {candidate_cfg}"
            assert candidate_cfg.resolve() != Path(base_config_csv).resolve(), (
                f"candidate_cfg == base_config_csv (swap broken) "
                f"candidate={candidate_cfg} base={base_config_csv}"
            )

            # apply regime
            df_r = _apply_regime(df0.copy(), classifier_module, candidate_cfg, base_config_csv)
            # Assicura r1/r5 prima del report (serve per STATS/PRO)
            df_r = _ensure_forward_returns(df_r, close_col="close")

            # report out for this trial
            report_csv = candidates_dir / f"trial_{t:04d}_report.csv"
            _write_report_reusing_existing(df_r, report_csv)


            # objective-based score (modulare)
            stats, coverage, n_by_regime, n_total = extract_inputs_for_objective(report_csv)

            obj = OBJECTIVES["simple_v09"](
                stats=stats,
                coverage=coverage,
                n_by_regime=n_by_regime,
                bands=target_bands,  # usa il dict target già presente in engine
                ctx={"n_total": n_total},
            )

            score = float(obj.score)

            metrics = _compute_trial_metrics(df_r, regime_col="REGIME_L1")

            # add objective breakdown (utile per ranking/debug)
            obj_break = obj.breakdown or {}

            # metrics serve per trials.csv (telemetry legacy)


            row = {
                "trial_id": t,
                "score": score,
                **{k: params[k] for k in sorted(space.keys())},
                "coverage_penalty": metrics.get("coverage_penalty", float("nan")),
                "chi2_pvalue": metrics.get("chi2_pvalue", float("nan")),
                "kruskal_r5_pvalue": metrics.get("kruskal_r5_pvalue", float("nan")),
                "max_abs_cliff_r5": metrics.get("max_abs_cliff_r5", float("nan")),
                "spread_r5_mean": metrics.get("spread_r5_mean", float("nan")),
                "report_csv": str(report_csv),
                "obj_hard_failed": int(obj.hard_failed),
                "obj_J_cov": obj_break.get("J_cov", float("nan")),
                "obj_J_chi2": obj_break.get("J_chi2", float("nan")),
                "obj_J_kr": obj_break.get("J_kr", float("nan")),
            }
            wr.writerow(row)

            tr = TrialResult(t, params, report_csv, metrics, score)
            if best is None or tr.score < best.score:
                best = tr

        if best is None:
            raise RuntimeError("Nessun trial eseguito.")

    # scrivi output finale _calibrated (parte dal BASE completo + override dei soli params ottimizzati)
    final_cfg = _make_calibrated_path(cfg_dir, base_config_csv)

    best_params = dict(best.params)

    # legacy bridge (difensivo): se mai arrivassero ancora bbw_* li mappiamo
    if "bbw_enter" in best_params and "bb_width_range_enter" not in best_params:
        best_params["bb_width_range_enter"] = best_params["bbw_enter"]
    if "bbw_exit" in best_params and "bb_width_range_exit" not in best_params:
        best_params["bb_width_range_exit"] = best_params["bbw_exit"]

    # ripulisci legacy keys
    best_params.pop("bbw_enter", None)
    best_params.pop("bbw_exit", None)

    # opzionale: se nel base esistono chiavi volatile basate su BBW, mantieni coerenza
    if "bb_width_range_enter" in best_params and "bb_width_volatile_enter" not in best_params:
        best_params["bb_width_volatile_enter"] = best_params["bb_width_range_enter"]
    if "bb_width_range_exit" in best_params and "bb_width_volatile_exit" not in best_params:
        best_params["bb_width_volatile_exit"] = best_params["bb_width_range_exit"]

    # scrittura: il base garantisce la presenza di TUTTI gli altri parametri (bb_period, bb_k, confirm_bars_*, ecc.)
    _write_config_from_base(base_config_csv, final_cfg, best_params)

    # copia report best
    best_report = best_dir / f"{Path(best.report_csv).stem}_calibrated.csv"
    shutil.copyfile(best.report_csv, best_report)

    return {
        "run_dir": str(run_dir),
        "trials_csv": str(trials_csv),
        "best_score": best.score,
        "best_config_csv": str(final_cfg),
        "best_report_csv": str(best_report),
    }