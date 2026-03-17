#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np

import scipy
from shared.regime_auto_calibration.regime_objectives import OBJECTIVES




print("\n[DEBUG INTERPRETER]")
print("sys.executable:", sys.executable)
print("sys.version:", sys.version)
print("scipy.__file__:", scipy.__file__)
print("scipy.__version__:", scipy.__version__)
print()



# ------------------------------------------------------------
# Formatter numerico standard (EU comma decimale)
# ------------------------------------------------------------
def _fmt(v):
    if v is None:
        return "None"
    try:
        if isinstance(v, float):
            return f"{v:.6f}".replace(".", ",")
        return str(v)
    except Exception:
        return str(v)


# ------------------------------------------------------------
# ANSI COLORS (terminal output)
# ------------------------------------------------------------
class _C:
    RESET  = "\033[0m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    BOLD   = "\033[1m"


def _color(text, color):
    return f"{color}{text}{_C.RESET}"


# --- bootstrap: garantisce import da Py_SUITE_TRADING root ---
SUITE_ROOT = Path(__file__).resolve().parents[1]  # cartella che contiene "shared"
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))


# ----------------------------
# Helpers UI
# ----------------------------

def _isatty() -> bool:
    try:
        import sys
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def _c(txt: str, code: str) -> str:
    """
    Colori ANSI per terminale.
    Se stdout non è TTY, ritorna testo plain.
    """
    if not _isatty():
        return txt
    return f"\x1b[{code}m{txt}\x1b[0m"


def _ok(txt: str) -> str:
    return _c(txt, "1;32")  # bold green


def _warn(txt: str) -> str:
    return _c(txt, "1;33")  # bold yellow


def _bad(txt: str) -> str:
    return _c(txt, "1;31")  # bold red


def _info(txt: str) -> str:
    return _c(txt, "1;36")  # bold cyan


def _muted(txt: str) -> str:
    return _c(txt, "2;37")  # dim gray


def _fmt_pvalue(p: float | None) -> str:
    if p is None:
        return _muted("N/A")
    if p < 0.05:
        return _ok(f"{p:.6g}")
    elif p < 0.10:
        return _warn(f"{p:.6g}")
    else:
        return _bad(f"{p:.6g}")


def _fmt_cliff(v: float) -> str:
    a = abs(v)
    if a >= 0.147:
        return _ok(f"{v:.4f}")
    elif a >= 0.10:
        return _warn(f"{v:.4f}")
    else:
        return _bad(f"{v:.4f}")


def _fmt_spread(v: float) -> str:
    if v > 0.001:
        return _ok(f"{v:.6f}")
    elif v > 0.0005:
        return _warn(f"{v:.6f}")
    else:
        return _bad(f"{v:.6f}")

def print_regime_validation_report(
    stats_sheet: pd.DataFrame,
    *,
    coverage_table: "pd.DataFrame | list[dict] | None" = None,
    title: str = "REGIME VALIDATION REPORT",
) -> dict:
    """Stampa *tutto* il report di validazione regime in UNICA funzione.

    Requisito progetto: la stampa del report deve essere centralizzata e richiamabile dall'esterno.
    Ritorna un dict con metriche/verdettto (utile per test/automation).
    """

    def _to_float(x, default=None):
        try:
            if x is None:
                return default
            s = str(x).strip()
            if s in ("", "nan", "None", "NaN"):
                return default
            # EU decimal -> float
            if s.startswith("<"):
                return 0.0
            return float(s.replace(",", "."))
        except Exception:
            return default

    def _get_metric(name: str):
        row = stats_sheet[stats_sheet["metric"] == name]
        if row.empty:
            return None
        return row["value"].iloc[0]

    # --- Normalizza coverage_table in DataFrame (se lista di dict)
    cov_df = None
    if coverage_table is not None:
        if hasattr(coverage_table, "columns"):
            cov_df = coverage_table  # type: ignore[assignment]
        elif isinstance(coverage_table, list):
            try:
                cov_df = pd.DataFrame(coverage_table)
            except Exception:
                cov_df = None

    # ------------------------------------------------------------
    # 1) Informatività (Kruskal/Cliff/Spread)
    # ------------------------------------------------------------
    kr_p = _to_float(_get_metric("kruskal_r5_pvalue"), default=None)
    kr_good = (kr_p is not None) and (kr_p < 0.05)

    cliff_vals = stats_sheet[
        stats_sheet["metric"].str.contains("cliff_r5_vs_best", na=False)
    ]["value"].tolist()
    cliff_vals = [_to_float(v, default=None) for v in cliff_vals]
    cliff_vals = [v for v in cliff_vals if v is not None]
    max_cliff = max([abs(v) for v in cliff_vals], default=0.0)

    r5_means = stats_sheet[
        stats_sheet["metric"].str.endswith(".r5_mean", na=False)
    ]["value"].tolist()
    r5_means = [_to_float(v, default=None) for v in r5_means]
    r5_means = [v for v in r5_means if v is not None]
    spread = (max(r5_means) - min(r5_means)) if len(r5_means) >= 2 else 0.0

    TH_CLIFF_GOOD = 0.15
    TH_SPREAD_GOOD = 0.0020
    effect_good = (max_cliff >= TH_CLIFF_GOOD)
    spread_good = (spread >= TH_SPREAD_GOOD)
    info_good = bool(kr_good and (effect_good or spread_good))

    # ------------------------------------------------------------
    # 2) Coverage vs Target (Chi²) + delta-to-band (se disponibile)
    # ------------------------------------------------------------
    chi2_p_cov = _to_float(_get_metric("chi2_pvalue"), default=None)
    coverage_off_target = (chi2_p_cov is not None) and (chi2_p_cov < 0.05)

    TARGET_KEYS = ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN"]

    def _extract_coverage_from_table(df_cov):
        # formato atteso: REGIME, STATUS, DELTA to band
        if df_cov is None or getattr(df_cov, "empty", True):
            return 0, 0.0, 0.0, []

        cols = {str(c).strip(): c for c in df_cov.columns}
        col_reg = cols.get("REGIME") or cols.get("regime")
        col_status = cols.get("STATUS") or cols.get("status")
        col_delta = (
            cols.get("DELTA to band")
            or cols.get("DELTA_TO_BAND")
            or cols.get("delta_to_band")
        )
        if not (col_reg and col_status and col_delta):
            return 0, 0.0, 0.0, []

        df = df_cov.copy()
        df[col_reg] = df[col_reg].astype(str).str.strip()
        df[col_status] = df[col_status].astype(str).str.strip().str.upper()
        df = df[df[col_reg].isin(TARGET_KEYS)]
        if df.empty:
            return 0, 0.0, 0.0, []

        deltas = []
        out_list = []
        for _, r in df.iterrows():
            st = str(r[col_status]).upper()
            d = _to_float(r[col_delta], default=0.0) or 0.0
            if st == "IN":
                d = 0.0
            elif st == "OUT":
                d = abs(d)
                out_list.append((r[col_reg], d))
            else:
                d = 0.0
            deltas.append(d)

        n_out = len(out_list)
        max_delta = max(deltas) if deltas else 0.0
        sum_delta = sum(deltas) if deltas else 0.0
        return n_out, max_delta, sum_delta, out_list

    def _extract_coverage_from_stats():
        # fallback: metriche coverage.<REGIME>.status / delta_to_band
        deltas = []
        out_list = []
        for reg in TARGET_KEYS:
            st = _get_metric(f"coverage.{reg}.status")
            st = str(st).strip().upper() if st is not None else None
            d = _to_float(_get_metric(f"coverage.{reg}.delta_to_band"), default=0.0) or 0.0
            if st == "IN":
                d = 0.0
            elif st == "OUT":
                d = abs(d)
                out_list.append((reg, d))
            else:
                d = 0.0
            deltas.append(d)

        n_out = len(out_list)
        max_delta = max(deltas) if deltas else 0.0
        sum_delta = sum(deltas) if deltas else 0.0
        return n_out, max_delta, sum_delta, out_list

    n_out, max_delta, sum_delta, out_list = _extract_coverage_from_table(cov_df)
    if n_out == 0 and max_delta == 0.0 and sum_delta == 0.0 and not out_list:
        n_out, max_delta, sum_delta, out_list = _extract_coverage_from_stats()

    unknown_obs = _to_float(_get_metric("coverage.UNKNOWN.observed_pct"), default=None)
    unknown_ok = True if unknown_obs is None else (unknown_obs <= 0.5)  # tolleranza micro 0,5%

    # ------------------------------------------------------------
    # 3) Regole A/B/C (calibrazione)
    # ------------------------------------------------------------
    TH_MAX_DELTA_B = 10.0
    TH_SUM_DELTA_B = 15.0
    TH_SUM_DELTA_C = 20.0
    TH_N_OUT_C = 3

    chi2_bad = coverage_off_target

    is_A = (n_out == 0) and (not chi2_bad) and (unknown_ok is True)
    is_B1 = (n_out >= 1) and (max_delta <= TH_MAX_DELTA_B) and (sum_delta <= TH_SUM_DELTA_B) and info_good
    is_B2 = (chi2_bad is True) and (max_delta <= TH_MAX_DELTA_B) and (n_out <= 2)
    is_B = (not is_A) and (is_B1 or is_B2)
    is_C1 = (max_delta > TH_MAX_DELTA_B) or (sum_delta > TH_SUM_DELTA_C) or (n_out >= TH_N_OUT_C)
    is_C2 = (unknown_ok is False)
    is_C3 = (info_good is False)
    is_C = (not is_A) and (not is_B) and (is_C1 or is_C2 or is_C3)

    if is_A:
        verdict = "A"
        verdict_msg = "✅ CALIBRAZIONE NON NECESSARIA"
    elif is_C:
        verdict = "C"
        verdict_msg = "⚠ CALIBRAZIONE ASSOLUTAMENTE NECESSARIA"
    else:
        verdict = "B"
        verdict_msg = "ℹ️ CALIBRAZIONE RACCOMANDATA"

    # ------------------------------------------------------------
    # 4) STAMPA REPORT (UNICA) — include: Auto A/B/C + verdict narrativo + summary/ranking
    # ------------------------------------------------------------
    print("\n" + _info(f"===== {title} ====="))

    # Auto verdict (A/B/C)
    # colore in base al livello (solo se TTY)
    if verdict == "A":
        head = _ok(verdict_msg)
    elif verdict == "B":
        head = _warn(verdict_msg)
    else:
        head = _bad(verdict_msg)

    print(head + _muted(f"  (level={verdict})"))

    reasons = []

    # label colorate (usa le funzioni già presenti: _ok/_warn/_bad)
    chi2_tag = _bad("BAD") if chi2_bad else _ok("OK")
    kr_tag = _ok("OK") if kr_good else _warn("NO")
    effect_tag = _ok("OK") if effect_good else _warn("NO")
    spread_tag = _ok("OK") if spread_good else _warn("NO")
    unk_tag = _bad("BAD") if (unknown_ok is False) else _ok("OK")

    if n_out > 0:
        out_str = ", ".join([f"{r} Δ={_fmt(d)}" for r, d in out_list]) if out_list else f"n_out={n_out}"
        reasons.append(f"coverage_out: {out_str} | maxΔ={_fmt(max_delta)} | sumΔ={_fmt(sum_delta)}")

    if chi2_p_cov is not None:
        reasons.append(f"chi2_pvalue_coverage={_fmt(chi2_p_cov)} ({_bad('BAD') if chi2_bad else _ok('OK')})")
    if kr_p is not None:
        reasons.append(f"kruskal_r5_pvalue={_fmt(kr_p)} ({_ok('OK') if kr_good else _warn('NO')})")
    reasons.append(f"max|cliff_r5|={_fmt(max_cliff)} ({_ok('OK') if effect_good else _warn('NO')})")
    reasons.append(f"spread_r5_mean={_fmt(spread)} ({_ok('OK') if spread_good else _warn('NO')})")
    if unknown_obs is not None:
        reasons.append(f"UNKNOWN_observed%={_fmt(unknown_obs)} ({_ok('OK') if unknown_ok else _bad('BAD')})")

    # Verdict narrativo (informatività + coverage)
    print("\n" + _info("-- Verdict (interpretazione) --"))
    if kr_p is not None and kr_p < 0.05 and max_cliff >= 0.147 and spread > 0.001:
        if coverage_off_target:
            print(_warn("⚠ Regimi informativi ma coverage fuori target (Chi²)"))
            print(_muted("  (Differenziazione statistica OK, ma calibrazione distribuzione consigliata)"))
        else:
            print(_ok("✔ Regimi differenziati in modo robusto"))
            print(_muted("  (Significatività statistica + effect size medio/grande + spread economico)"))
    elif max_cliff >= 0.10 and spread > 0.0005:
        print(_warn("⚠ Differenze moderate (possibile segnale, da monitorare)"))
    else:
        print(_bad("✖ Nessuna evidenza solida di differenziazione tra regimi"))

    print(_info("  kruskal_pvalue_r5: ") + _fmt_pvalue(kr_p))
    print(_info("  max|cliff_r5|: ") + _fmt_cliff(max_cliff))
    print(_info("  spread r5_mean: ") + _fmt_spread(spread))
    if coverage_off_target:
        p_txt = "< 1e-6" if (chi2_p_cov is not None and chi2_p_cov < 1e-6) else _fmt(chi2_p_cov)
        print(_info("  chi2_pvalue_coverage: ") + _warn(p_txt))

    # Summary by regime (PRO) + ranking
    print("\n" + _info("-- Summary by Regime (PRO) --"))
    print(_muted("(Statistiche forward return r1/r5 per regime."))
    print(_muted(" r*_hit = probabilità di rendimento positivo."))
    print(_muted(" cliff5 = effect size vs miglior regime (range [-1,+1]).)"))

    regime_metrics = stats_sheet[stats_sheet["metric"].str.contains(r"\.")]
    regimes = sorted(set(str(m).split(".")[0] for m in regime_metrics["metric"]))

    def _get(reg, suffix):
        row = stats_sheet[stats_sheet["metric"] == f"{reg}.{suffix}"]
        if row.empty:
            return ""
        return _fmt(row["value"].iloc[0])

    cols = [
        ("N", "n", 6),
        ("r1_mean", "r1_mean", 12),
        ("r1_med", "r1_median", 10),
        ("r1_std", "r1_std", 10),
        ("r1_hit", "r1_hit_rate", 9),
        ("r5_mean", "r5_mean", 12),
        ("r5_med", "r5_median", 10),
        ("r5_std", "r5_std", 10),
        ("r5_hit", "r5_hit_rate", 9),
        ("cliff5", "cliff_r5_vs_best", 9),
    ]

    header = f"{'REGIME':12s} | " + " | ".join([f"{c[0]:>{c[2]}s}" for c in cols])
    print(_info(header))
    print(_muted("-" * len(header)))

    ranking = []
    for reg in regimes:
        r5m = stats_sheet[stats_sheet["metric"] == f"{reg}.r5_mean"]["value"]
        r5m = _to_float(r5m.iloc[0], default=np.nan) if (not r5m.empty) else np.nan
        ranking.append((reg, r5m))

    ranking_clean = [(r, v) for r, v in ranking if v == v]
    best_reg = max(ranking_clean, key=lambda x: x[1])[0] if ranking_clean else None
    worst_reg = min(ranking_clean, key=lambda x: x[1])[0] if ranking_clean else None

    for reg in regimes:
        reg_u = str(reg).strip().upper()
        tag = ""
        color_fn = None

        if best_reg and reg == best_reg:
            tag = " ★"
            color_fn = _ok
        elif worst_reg and reg == worst_reg:
            tag = " ⚠"
            color_fn = _bad
        elif reg_u == "VOLATILE":
            tag = " ⚠"
            color_fn = _warn

        line = f"{(str(reg) + tag):12s} | " + " | ".join([f"{_get(reg, c[1]):>{c[2]}s}" for c in cols])
        print(color_fn(line) if color_fn else line)

    if ranking_clean:
        ranking_sorted = sorted(ranking_clean, key=lambda x: x[1], reverse=True)

        def _print_rank(title, items):
            print(f"\n-- {title} --")
            print(f"{'REGIME':12s} | {'r5_mean':>12s}")
            print("-" * 28)
            for r, v in items:
                print(f"{r:12s} | {_fmt(v):>12s}")

        top_n = min(5, len(ranking_sorted))
        bot_n = min(5, len(ranking_sorted))
        _print_rank("Top", ranking_sorted[:top_n])
        if bot_n > 0:
            _print_rank("Bottom", list(reversed(ranking_sorted[-bot_n:])))

    return {
        "verdict": verdict,
        "verdict_msg": verdict_msg,
        "chi2_pvalue_coverage": chi2_p_cov,
        "kruskal_r5_pvalue": kr_p,
        "max_cliff_r5": max_cliff,
        "spread_r5_mean": spread,
        "n_out": n_out,
        "max_delta": max_delta,
        "sum_delta": sum_delta,
        "unknown_observed_pct": unknown_obs,
    }

def _isatty() -> bool:
    try:
        import sys
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def _c(txt: str, code: str) -> str:
    if not _isatty():
        return txt
    return f"\x1b[{code}m{txt}\x1b[0m"

# ------------------------------------------------------------
# ANSI color helpers (terminal/log)
# ------------------------------------------------------------
import os
import sys

def _use_color() -> bool:
    """
    Decide se usare ANSI colors.
    - Se FORCE_COLOR=1 -> SEMPRE
    - Se NO_COLOR=1 -> MAI
    - Se stdout è TTY -> SI
    - Fallback macOS: TERM != dumb -> SI (utile per .command / launcher log)
    """
    if os.environ.get("NO_COLOR", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
        return False
    if os.environ.get("FORCE_COLOR", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
        return True

    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if is_tty:
        return True

    term = os.environ.get("TERM", "").strip().lower()
    if term and term != "dumb":
        return True

    return False

_USE_COLOR = _use_color()

def _c(s: str, code: str) -> str:
    if not _USE_COLOR:
        return s
    return f"{code}{s}\033[0m"

def _ok(s: str) -> str:
    return _c(s, "\033[32m")  # green

def _warn(s: str) -> str:
    return _c(s, "\033[33m")  # yellow

def _bad(s: str) -> str:
    return _c(s, "\033[31m")  # red

def _info(s: str) -> str:
    return _c(s, "\033[36m")  # cyan

def _muted(s: str) -> str:
    return _c(s, "\033[90m")  # grey

def _fmt_pvalue(p: float | None) -> str:
    if p is None:
        return _muted("N/A")
    if p < 0.05:
        return _ok(f"{p:.6g}")
    elif p < 0.10:
        return _warn(f"{p:.6g}")
    else:
        return _bad(f"{p:.6g}")


def _fmt_cliff(v: float) -> str:
    a = abs(v)
    if a >= 0.147:
        return _ok(f"{v:.4f}")
    elif a >= 0.10:
        return _warn(f"{v:.4f}")
    else:
        return _bad(f"{v:.4f}")


def _fmt_spread(v: float) -> str:
    if v > 0.001:
        return _ok(f"{v:.6f}")
    elif v > 0.0005:
        return _warn(f"{v:.6f}")
    else:
        return _bad(f"{v:.6f}")

def _safe_import_scipy_stats():
    """
    Import robusto di scipy.stats.
    Ritorna:
      - stats module se disponibile e coerente
      - None se SciPy non è installato / importabile
    Nota: non catturiamo Exception generiche per evitare falsi "no scipy".
    """
    try:
        from scipy import stats  # type: ignore
    except (ImportError, ModuleNotFoundError):
        return None

    # Sanity-check: le funzioni PRO devono esistere
    if not hasattr(stats, "kruskal") or not hasattr(stats, "chi2_contingency"):
        return None

    return stats


def _build_regime_validation_stats_sheet(
    df: pd.DataFrame,
    *,
    regime_col: str,
    coverage_pct: dict,
    targets: dict,
) -> pd.DataFrame:
    """
    Costruisce un foglio verticale metric/value con indicatori statistici di validazione.
    Non deve mai crashare: se manca SciPy o colonne, ritorna metriche N/A.
    """
    rows = []

    def add(metric: str, value) -> None:
        rows.append({"metric": metric, "value": value})

    # --- basic checks
    if regime_col not in df.columns:
        add("stats_available", "NO")
        add("reason", f"missing column {regime_col}")
        return pd.DataFrame(rows)

    # ------------------------------------------------------------
    # 1) Chi-square: observed vs expected (midpoint target)
    #    NB: i target sono range; questo è un check INDICATIVO.
    # ------------------------------------------------------------
    stats = _safe_import_scipy_stats()
    if stats is None:
        add("scipy_available", "NO")
    else:
        add("scipy_available", "YES")

    # usa solo i regimi con target numerico (non n/a)
    # targets dict in forma: {"TREND": (25,45), ... , "TREND_UP": None, ...}
    exp_keys: list[str] = []
    exp_pct: list[float] = []
    obs_counts: list[int] = []
    total = int(len(df))

    # Chi² output vars (sempre definite per il verdict)
    chi2_stat: float | None = None
    chi2_p_cov: float | None = None

    sreg = df[regime_col].astype(str).str.strip().str.upper()
    vc = sreg.value_counts(dropna=False)

    for k, band in targets.items():
        if band is None:
            continue
        try:
            lo, hi = float(band[0]), float(band[1])
        except Exception:
            continue
        mid = (lo + hi) / 2.0
        exp_keys.append(str(k))
        exp_pct.append(float(mid))
        obs_counts.append(int(vc.get(str(k), 0)))

    if exp_keys and total > 0:
        # Observed total SOLO sui regimi con target (altrimenti somma != expected)
        obs_total = int(sum(obs_counts))

        add("chi2_target_keys", ",".join(exp_keys))
        add("chi2_total_rows", total)
        add("chi2_obs_total_used", obs_total)

        if stats is not None and obs_total > 0:
            try:
                # Midpoint target -> pesi relativi (rinormalizzati), poi convertiti in counts su obs_total
                w = [max(0.0, float(p)) for p in exp_pct]
                w_sum = float(sum(w))

                if w_sum <= 0:
                    raise ValueError("expected_weights_sum_zero")

                exp_counts = [obs_total * (p / w_sum) for p in w]

                # Evita zeri (stabilità numerica). Mantiene somma uguale a obs_total.
                eps = 1e-9
                exp_counts = [max(eps, x) for x in exp_counts]
                scale = obs_total / float(sum(exp_counts))
                exp_counts = [x * scale for x in exp_counts]

                chi2_res = stats.chisquare(f_obs=obs_counts, f_exp=exp_counts)
                chi2_stat = float(chi2_res.statistic)
                chi2_p_cov = float(chi2_res.pvalue)

                add("chi2_stat", chi2_stat)
                add("chi2_pvalue", chi2_p_cov)

            except Exception as ex:
                chi2_stat = None
                chi2_p_cov = None
                add("chi2_stat", "N/A")
                add("chi2_pvalue", f"N/A ({type(ex).__name__})")
        else:
            chi2_stat = None
            chi2_p_cov = None
            add("chi2_stat", "N/A")
            add("chi2_pvalue", "N/A")
    else:
        chi2_stat = None
        chi2_p_cov = None
        add("chi2_stat", "N/A")
        add("chi2_pvalue", "N/A")

    # ------------------------------------------------------------
    # 2) Kruskal-Wallis su forward returns r1 e r5
    # ------------------------------------------------------------
    if "close" not in df.columns:
        add("kruskal_r1_stat", "N/A")
        add("kruskal_r1_pvalue", "N/A (missing close)")
        add("kruskal_r5_stat", "N/A")
        add("kruskal_r5_pvalue", "N/A (missing close)")
        return pd.DataFrame(rows)

    close = pd.to_numeric(df["close"], errors="coerce")
    r1 = close.shift(-1) / close - 1.0
    r5 = close.shift(-5) / close - 1.0

    # gruppi per regime con almeno un minimo di dati
    def _groups(x: pd.Series, min_n: int = 30):
        g = []
        keys = []
        for reg, sub in x.groupby(sreg):
            vals = sub.dropna().values
            if len(vals) >= min_n:
                g.append(vals)
                keys.append(str(reg))
        return keys, g

    if stats is None:
        add("kruskal_r1_stat", "N/A")
        add("kruskal_r1_pvalue", "N/A (no scipy)")
        add("kruskal_r5_stat", "N/A")
        add("kruskal_r5_pvalue", "N/A (no scipy)")
    else:
        k1, g1 = _groups(r1)
        k5, g5 = _groups(r5)

        add("kruskal_min_n_per_group", 30)

        if len(g1) >= 2:
            try:
                res1 = stats.kruskal(*g1)
                add("kruskal_r1_groups", ",".join(k1))
                add("kruskal_r1_stat", float(res1.statistic))
                add("kruskal_r1_pvalue", float(res1.pvalue))
            except Exception as ex:
                add("kruskal_r1_stat", "N/A")
                add("kruskal_r1_pvalue", f"N/A ({type(ex).__name__})")
        else:
            add("kruskal_r1_stat", "N/A")
            add("kruskal_r1_pvalue", "N/A (insufficient groups)")

        if len(g5) >= 2:
            try:
                res5 = stats.kruskal(*g5)
                add("kruskal_r5_groups", ",".join(k5))
                add("kruskal_r5_stat", float(res5.statistic))
                add("kruskal_r5_pvalue", float(res5.pvalue))
            except Exception as ex:
                add("kruskal_r5_stat", "N/A")
                add("kruskal_r5_pvalue", f"N/A ({type(ex).__name__})")
        else:
            add("kruskal_r5_stat", "N/A")
            add("kruskal_r5_pvalue", "N/A (insufficient groups)")

    # ------------------------------------------------------------
    # 3) Summary by regime + hit-rate
    # ------------------------------------------------------------
    tmp = pd.DataFrame({regime_col: sreg, "r1": r1, "r5": r5})

    def _hit_rate(x: pd.Series) -> float:
        x = x.dropna()
        if len(x) == 0:
            return np.nan
        return float((x > 0).mean())

    # Cliff's delta (puro numpy, no scipy)
    def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
        # delta = P(a>b) - P(a<b)
        if a.size == 0 or b.size == 0:
            return np.nan
        # approccio O(n*m): per i nostri N tipici (centinaia) è ok
        gt = 0
        lt = 0
        for x in a:
            gt += int((x > b).sum())
            lt += int((x < b).sum())
        denom = a.size * b.size
        return float((gt - lt) / denom) if denom else np.nan

    # calcola summary
    regimes = sorted(tmp[regime_col].dropna().unique())
    for reg in regimes:
        sub = tmp[tmp[regime_col] == reg]

        add(f"{reg}.n", int(sub["r1"].notna().sum()))

        # r1 stats
        add(f"{reg}.r1_mean", float(sub["r1"].mean()) if sub["r1"].notna().any() else np.nan)
        add(f"{reg}.r1_median", float(sub["r1"].median()) if sub["r1"].notna().any() else np.nan)
        add(f"{reg}.r1_std", float(sub["r1"].std()) if sub["r1"].notna().any() else np.nan)
        add(f"{reg}.r1_hit_rate", _hit_rate(sub["r1"]))

        # r5 stats
        add(f"{reg}.r5_mean", float(sub["r5"].mean()) if sub["r5"].notna().any() else np.nan)
        add(f"{reg}.r5_median", float(sub["r5"].median()) if sub["r5"].notna().any() else np.nan)
        add(f"{reg}.r5_std", float(sub["r5"].std()) if sub["r5"].notna().any() else np.nan)
        add(f"{reg}.r5_hit_rate", _hit_rate(sub["r5"]))

    # ------------------------------------------------------------
    # 4) Effect size (Cliff's delta) vs BEST regime (by r5_mean)
    # ------------------------------------------------------------
    # identifica best regime su r5_mean (richiede dati)
    best_reg = None
    best_val = -np.inf
    for reg in regimes:
        v = tmp.loc[tmp[regime_col] == reg, "r5"].mean(skipna=True)
        if v == v and float(v) > best_val:
            best_val = float(v)
            best_reg = reg

    add("effect_best_regime_r5_mean", best_reg if best_reg is not None else "N/A")

    if best_reg is not None:
        best_r5 = tmp.loc[tmp[regime_col] == best_reg, "r5"].dropna().values
        best_r1 = tmp.loc[tmp[regime_col] == best_reg, "r1"].dropna().values

        for reg in regimes:
            if reg == best_reg:
                add(f"{reg}.cliff_r5_vs_best", 0.0)
                add(f"{reg}.cliff_r1_vs_best", 0.0)
                continue

            a5 = tmp.loc[tmp[regime_col] == reg, "r5"].dropna().values
            a1 = tmp.loc[tmp[regime_col] == reg, "r1"].dropna().values

            add(f"{reg}.cliff_r5_vs_best", _cliffs_delta(a5, best_r5))
            add(f"{reg}.cliff_r1_vs_best", _cliffs_delta(a1, best_r1))
    else:
        for reg in regimes:
            add(f"{reg}.cliff_r5_vs_best", np.nan)
            add(f"{reg}.cliff_r1_vs_best", np.nan)

    return pd.DataFrame(rows)


def _ask_yes_no(prompt: str, default_yes: bool = False) -> bool:
    d = "Y/n" if default_yes else "y/N"
    raw = input(f"{prompt} [{d}]: ").strip().lower()
    if not raw:
        return default_yes
    return raw in ("y", "yes", "s", "si")


def _ask_path(prompt: str, default: Path) -> Path:
    raw = input(f"{prompt}\nDefault: {default}\nConfermi? [Y/n] (invio=Y): ").strip().lower()
    if raw in ("", "y", "yes"):
        return default
    raw2 = input("Inserisci nuovo path: ").strip()
    return Path(raw2).expanduser().resolve()


def _pick_file_interactive(dir_: Path, prefix: str) -> Path:
    files = sorted([p for p in dir_.glob(f"{prefix}*.csv") if p.is_file()])
    if not files:
        raise FileNotFoundError(f"Nessun file trovato in {dir_} con prefisso {prefix}*.csv")

    print(f"\nSeleziona file ({prefix}*.csv) in: {dir_}")
    for i, f in enumerate(files, 1):
        print(f"  {i:2d}) {f.name}")
    while True:
        raw = input("Scelta (numero): ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(files):
                return files[idx - 1]
        print("Scelta non valida.")


# ----------------------------
# Regime selection + apply
# ----------------------------
def _pick_regime_module(shared_dir: Path) -> str:
    # Import qui per evitare errori se lanciato fuori suite root
    from shared.loader_regime import list_regime_modules

    mods = list_regime_modules(shared_dir)  # deve già filtrare per regime_*
    if not mods:
        raise RuntimeError(f"Nessun modulo regime_* trovato in {shared_dir}")

    print("\nSeleziona un filtro di regime (solo file che iniziano per regime_)")
    for i, m in enumerate(mods, 1):
        print(f"  {i:2d}) {m}")
    while True:
        raw = input("Scelta (numero): ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(mods):
                return mods[idx - 1]
        print("Scelta non valida.")


def _load_regime_apply(regime_module: str, shared_dir: Path):
    from shared.loader_regime import load_regime_apply
    return load_regime_apply(shared_dir, regime_module)



# ----------------------------
# Strategy Creator report imports (robusti)
# ----------------------------
def _import_report_tools(suite_root: Path):
    """
    Import robusto del report builder + writer.
    Assumiamo repo: Py_SUITE_TRADING/5. Strategy Creator/strategy_creator/src/...
    """
    sc_src = suite_root / "5. Strategy Creator" / "strategy_creator" / "src"
    if sc_src.exists():
        sys.path.insert(0, str(sc_src))

    from regime_filter_report.report import build_regime_report
    from regime_filter_report.io_utils import write_single_csv_report
    return build_regime_report, write_single_csv_report

from shared.regime_auto_calibration.engine import _get_default_target_bands

def build_regime_output_path(in_file: Path) -> Path:
    """
    Costruisce il path del CSV operativo post-regime
    da usare poi in Run_strategia.
    """
    parent = in_file.parent
    stem = in_file.stem

    if stem.startswith("KPI_"):
        out_name = f"KPI_REGIME_{stem[4:]}.csv"
    else:
        out_name = f"KPI_REGIME_{stem}.csv"

    return parent / out_name

# ============================================================
# REGIME_L1 – Target di riferimento
# Include tutti i regimi canonici + fallback UNKNOWN
# ============================================================
REGIME_L1_TARGETS = {
    "TREND":    (25.0, 45.0),
    "RANGE":    (30.0, 55.0),
    "LATERAL":  (30.0, 55.0),
    "VOLATILE": (0.0, 20.0),
    "UNKNOWN":  (0.0,  0.0),
}

def get_regime_l1_targets(timeframe: str) -> Dict[str, Tuple[float, float]]:
    """
    Ritorna le bande target per REGIME_L1 in base al timeframe.
    Prima prova ad allinearsi all'engine (shared.regime_auto_calibration.engine),
    altrimenti fallback al comportamento legacy del wizard.
    """
    tf = (timeframe or "").strip().lower()
    tf = tf.replace("30min", "30m").replace("1day", "1d").replace("1hour", "1h").replace("1week", "1w")

    # 1) Source of truth: engine (se disponibile)
    try:
        from shared.regime_auto_calibration.engine import _get_default_target_bands
        bands = _get_default_target_bands(tf)
        if isinstance(bands, dict) and bands:
            return bands
    except Exception:
        pass

    # 2) Legacy fallback (wizard-local)
    tf_map = globals().get("REGIME_L1_TARGETS_BY_TF", None)
    if isinstance(tf_map, dict) and tf in tf_map:
        return tf_map[tf]

    return REGIME_L1_TARGETS


def _extract_regime_coverage_pct_from_sheets(sheets: dict, *, regime_col: str) -> dict[str, float]:
    """
    Estrae la coverage (%) dalla tabella REGIME_COVERAGE (trasposta).
    Atteso: sheets["REGIME_COVERAGE"] con prima colonna = regime_col e una riga con regime_col=='share'.
    """
    cov_t = sheets.get("REGIME_COVERAGE")
    if cov_t is None or getattr(cov_t, "empty", True):
        return {}

    if regime_col not in cov_t.columns:
        return {}

    share_rows = cov_t[cov_t[regime_col].astype(str).str.strip().str.lower().eq("share")]
    if share_rows.empty:
        return {}

    r = share_rows.iloc[0]
    out = {}
    for c in cov_t.columns:
        if c == regime_col:
            continue
        try:
            v = float(r[c])
        except Exception:
            v = 0.0
        out[str(c)] = v * 100.0  # share (0..1) -> percent

    # ------------------------------------------------------------
    # REGIME1: garantisci chiavi canoniche anche se 0% + TREND aggregation
    # ------------------------------------------------------------
    # Canonici REGIME1 (percentuali)
    canonical = ["VOLATILE", "TREND_UP", "TREND_DOWN", "RANGE", "LATERAL", "UNKNOWN", "TREND"]

    # normalizza missing a 0.0
    for k in canonical:
        out.setdefault(k, 0.0)

    # aggrega TREND = TREND_UP + TREND_DOWN (se presenti)
    out["TREND"] = float(out.get("TREND_UP", 0.0) or 0.0) + float(out.get("TREND_DOWN", 0.0) or 0.0)

    # opzionale: rimuovi eventuali chiavi sporche (spazi)
    out = {str(k).strip().upper(): float(v or 0.0) for k, v in out.items()}

    return out
def print_regime_coverage_table_vs_target(
     regime_coverage_pct: dict[str, float],
     *,
     timeframe_label: str = "30m",
) -> tuple[list[dict], list[tuple[str, float]]]:

    targets = get_regime_l1_targets(timeframe_label)
    regimes = list(targets.keys())
    extras = sorted([r for r in regime_coverage_pct.keys() if r not in targets])
    regimes += extras

    coverage_table: list[dict] = []
    out_of_target: list[tuple[str, float]] = []  # (REGIME, DELTA_to_band_abs)

    print(f"\n[REGIME][TARGET] Range di riferimento (timeframe {timeframe_label}):")
    for r in regimes:
        if r in targets:
            lo, hi = targets[r]
            print(f"- {r:<12}: {lo:.0f}% – {hi:.0f}%")
        else:
            print(f"- {r:<12}: n/a")

    print(f"\n[REGIME][TABLE] Coverage osservata vs target (timeframe {timeframe_label})")
    header = f"{'REGIME':<12} | {'OBSERVED %':>10} | {'TARGET %':>13} | {'DELTA to band':>13} | {'STATUS':<6}"
    print(header)
    print("-" * len(header))

    for r in regimes:
        obs = float(regime_coverage_pct.get(r, 0.0) or 0.0)

        if r in targets:
            lo, hi = targets[r]
            target_str = f"{lo:.0f}–{hi:.0f}"

            if obs < lo:
                delta_to_band = lo - obs
                status = "OUT"
            elif obs > hi:
                delta_to_band = obs - hi
                status = "OUT"
            else:
                delta_to_band = 0.0
                status = "IN"
        else:
            target_str = "n/a"
            delta_to_band = 0.0
            status = "N/A"

        # salva tabella strutturata (serve al verdetto A/B/C)
        coverage_table.append({
            "REGIME": r,
            "OBSERVED %": obs,
            "TARGET %": target_str,
            "DELTA to band": delta_to_band,
            "STATUS": status,
            "TARGET_LO": (targets[r][0] if r in targets else None),
            "TARGET_HI": (targets[r][1] if r in targets else None),
        })

        # lista regimi fuori target (solo quelli con target)
        if (r in targets) and (status == "OUT"):
            out_of_target.append((r, float(delta_to_band)))

        # stampa riga
        print(f"{r:<12} | {obs:>10.2f} | {target_str:>13} | {delta_to_band:>13.2f} | {status:<6}")

    if out_of_target:
        print("\n[REGIME][STATUS] ⚠ CALIBRAZIONE NECESSARIA")
        print("[REGIME][DETAIL] Regimi fuori target:", ", ".join([r for r, _ in out_of_target]))
    else:
        print("\n[REGIME][STATUS] ✓ Coverage entro i range target")

    return coverage_table, out_of_target


def print_regime_wizard_report(
    df_r: pd.DataFrame,
    *,
    timeframe_label: str,
    targets: dict[str, tuple[float, float]],
    stats_sheet: pd.DataFrame,
    coverage_table: list[dict] | None = None,
    rows_total: int | None = None,
    rows_allowed: int | None = None,
    rows_blocked: int | None = None,
    pct_blocked: float | None = None,
    targets_fallback_warn: str | None = None,
    show_verdict: bool = True,
) -> dict:
    """
    STAMPA COMPLETA wizard-style in UNICA funzione pubblica richiamabile dall'esterno.

    Ripristina output storico:
    - ===== REGIME FILTER IMPACT =====
    - [REGIME][WARN] (se presente)
    - [REGIME][TARGET] + [REGIME][TABLE] + [REGIME][STATUS]
    - ===== REGIME FILTER VALIDATION (STATS) =====
      -- Chi2 vs Target --
      -- Kruskal Tests --
    Opzionale: show_verdict=True stampa anche il blocco A/B/C (nuovo).
    Ritorna un dict payload (utile per test/pipeline).
    """

    # ---------------------------
    # IMPACT
    # ---------------------------
    if rows_total is None:
        rows_total = int(len(df_r))
    if rows_allowed is None:
        rows_allowed = int(rows_total)
    if rows_blocked is None:
        rows_blocked = int(0)
    if pct_blocked is None:
        pct_blocked = float(0.0)

    print("\n===== REGIME FILTER IMPACT =====")
    print(f"rows_total: {rows_total}")
    print(f"rows_allowed: {rows_allowed}")
    print(f"rows_blocked: {rows_blocked}")
    print(f"pct_blocked: {pct_blocked}")

    # ---------------------------
    # TARGET warning (fallback)
    # ---------------------------
    if targets_fallback_warn:
        print(targets_fallback_warn)

    # ---------------------------
    # COVERAGE TABLE + STATUS
    # ---------------------------
    # compute coverage pct from df_r (assume colonna REGIME_L1 o REGIME_L1_RAW)
    regime_col = "REGIME_L1" if "REGIME_L1" in df_r.columns else ("REGIME_L1_RAW" if "REGIME_L1_RAW" in df_r.columns else None)
    if not regime_col:
        raise ValueError("[REGIME][REPORT] colonna regime non trovata (attese: REGIME_L1 o REGIME_L1_RAW)")

    cov = (
        df_r[regime_col]
        .astype(str)
        .str.strip()
        .str.upper()
        .replace({"": "UNKNOWN", "NAN": "UNKNOWN", "NONE": "UNKNOWN"})
    )
    regime_coverage_pct = (cov.value_counts(normalize=True) * 100.0).to_dict()

    # --- ALIGN WITH ENGINE: canonical keys + TREND aggregation ---
    # normalizza chiavi
    regime_coverage_pct = {str(k).strip().upper(): float(v or 0.0) for k, v in regime_coverage_pct.items()}

    # garantisci chiavi canoniche
    for k in ["VOLATILE", "TREND_UP", "TREND_DOWN", "RANGE", "LATERAL", "UNKNOWN"]:
        regime_coverage_pct.setdefault(k, 0.0)

    # aggrega TREND = TREND_UP + TREND_DOWN
    regime_coverage_pct["TREND"] = float(regime_coverage_pct.get("TREND_UP", 0.0) or 0.0) + float(
        regime_coverage_pct.get("TREND_DOWN", 0.0) or 0.0)

    # usa la funzione esistente che stampa target/table/status e ritorna coverage_table/out_list
    coverage_table2, out_of_target = print_regime_coverage_table_vs_target(
        regime_coverage_pct,
        timeframe_label=timeframe_label,
    )

    # ---------------------------
    # VALIDATION (STATS) - stampa come prima
    # ---------------------------
    print("\n===== REGIME FILTER VALIDATION (STATS) =====")

    # Chi2 block
    chi2_block = stats_sheet[stats_sheet["metric"].astype(str).str.startswith("chi2_")]
    if not chi2_block.empty:
        print("\n-- Chi2 vs Target --")
        print("(Test di aderenza tra distribuzione osservata e midpoint dei target.")
        print(" p-value < 0,05 → distribuzione significativamente diversa dal target.)")
        for _, r in chi2_block.iterrows():
            print(f"{str(r['metric']):20s} | {r['value']}")

    # Kruskal block
    kr_block = stats_sheet[stats_sheet["metric"].astype(str).str.startswith("kruskal_")]
    if not kr_block.empty:
        print("\n-- Kruskal Tests --")
        print("(Test non parametrico di differenza tra regimi sui forward returns.")
        print(" p-value < 0,05 → almeno un regime differisce in modo significativo.)")
        for _, r in kr_block.iterrows():
            print(f"{str(r['metric']):20s} | {r['value']}")

    # ---------------------------
    # VERDICT + TABELLE COLORATE (PRO) — UNA SOLA VOLTA
    # ---------------------------
    verdict_payload = {}
    if show_verdict:
        verdict_payload = print_regime_validation_report(
            stats_sheet,
            coverage_table=(coverage_table or coverage_table2),
            title="REGIME VALIDATION VERDICT",
        ) or {}

    return {
        "rows_total": rows_total,
        "rows_allowed": rows_allowed,
        "rows_blocked": rows_blocked,
        "pct_blocked": pct_blocked,
        "timeframe_label": timeframe_label,
        "out_of_target": out_of_target,
        "coverage_table": coverage_table2,
        "verdict": verdict_payload,
    }

def print_regime_wizard_style_summary_from_config(
    *,
    input_csv: str,
    config_csv: str,
    timeframe: str = "1d",
    classifier_module: str = "shared.regime_classifier_1",
) -> None:
    """
    Wrapper pubblico (no-duplica-logica) per stampare:
    - REGIME FILTER IMPACT
    - TARGET + Coverage table + STATUS (riusa print_regime_coverage_table_vs_target)
    - VALIDATION STATS + VERDICT + SUMMARY (riusa builder interno stats sheet)
    """
    from pathlib import Path
    import importlib
    import pandas as pd

    input_csv = str(input_csv)
    config_csv = str(config_csv)

    # 1) Load data
    df0 = pd.read_csv(input_csv)

    # 2) Params dal config CSV (riusa loader già presente nel classifier core)
    core = importlib.import_module(classifier_module)

    # resolve params dal CSV: nei tuoi moduli core esiste _load_filter_defaults_from_csv()
    # e apply_regime_L1 accetta cfg_keys dict con chiavi param->value.
    # Qui non replichiamo parser: usiamo la stessa funzione del core se esposta,
    # altrimenti fallback minimale tramite _import_report_tools (che nel wizard già esiste).
    params = None

    if hasattr(core, "_load_filter_defaults_from_csv"):
        # swap temporaneo: forziamo il core a leggere quel config_csv (pattern già usato altrove)
        # ma SOLO se il core legge da path fisso; se supporta argomento path, meglio.
        try:
            params = core._load_filter_defaults_from_csv(Path(config_csv))  # type: ignore
        except TypeError:
            # fallback: se la funzione non accetta path, usa tool del wizard (parser CSV già usato nel report)
            rt = _import_report_tools()
            params = rt.parse_config_csv_to_params(Path(config_csv))  # type: ignore
    else:
        rt = _import_report_tools()
        params = rt.parse_config_csv_to_params(Path(config_csv))  # type: ignore

    if not params:
        raise ValueError(f"[WIZARD_SUMMARY] params vuoti da config_csv={config_csv}")

    # 3) Applica regime via core (senza duplicare logica)
    # Firma del tuo core: apply_regime_L1(df, regime_filter="L1", cfg_keys=...)
    try:
        df_r = core.apply_regime_L1(df0.copy(), regime_filter="L1", cfg_keys=params)  # type: ignore
    except TypeError:
        # fallback firma posizionale (più robusta)
        df_r = core.apply_regime_L1(df0.copy(), "L1", params)  # type: ignore

    # ---------------------------
    # IMPACT (wizard style)
    # ---------------------------
    rows_total = len(df_r)
    rows_allowed = rows_total
    rows_blocked = 0
    pct_blocked = 0.0


    # ---------------------------
    # STATS + VERDICT + SUMMARY (riuso builder interno)
    # ---------------------------
    # Il wizard già costruisce uno "stats_sheet" in stile report.
    # Qui lo generiamo e lo stampiamo in console.
    try:
        stats_sheet = _build_regime_validation_stats_sheet(df_r)  # type: ignore
    except TypeError:
        # se richiede regime_col o altri argomenti, prova a passarli
        stats_sheet = _build_regime_validation_stats_sheet(df_r, regime_col="REGIME_L1")  # type: ignore

    # stampa sheet come fa il wizard (riusiamo formatter del wizard se esiste)
    print("\n===== REGIME FILTER VALIDATION (STATS) =====")
    # se lo sheet è DataFrame con colonne metric/value
    if hasattr(stats_sheet, "iterrows"):
        for _, r in stats_sheet.iterrows():
            m = str(r.get("metric", ""))
            v = r.get("value", "")
            if m:
                print(f"{m:20s} | {v}")
    else:
        # fallback string/lines
        print(stats_sheet)



# ----------------------------
# MAIN
# ----------------------------
def main() -> int:
    chi2_p_cov = None

    # suite_root = cartella che contiene "shared"
    suite_root = Path(__file__).resolve().parents[1]
    shared_dir = suite_root / "shared"
    default_in_repo = suite_root / "_data" / "Test Data"
    default_out_repo = suite_root / "_data" / "config_filtro_regime"


    print("======================================")
    print(" Regime Filter Wizard (apply + report)")
    print("======================================")

    # STEP 1: scegli filtro regime_* da /shared
    # con retry se il filtro scelto fallisce in fase di apply
    while True:
        regime_module = _pick_regime_module(shared_dir)
        apply_fn = _load_regime_apply(regime_module, shared_dir)

        # STEP 2: change defaults? (stub)
        if _ask_yes_no("Vuoi cambiare i valori di default?", default_yes=False):
            print("\n[TODO] Routine 'Filtro Regime – modifica parametri' non ancora implementata.")
            print("      Proseguo con i default del modulo.\n")
            # in futuro: qui generi/aggiorni un dict config e lo passi ad apply_fn(df, config=...)

        # STEP 3: repo input
        in_repo = _ask_path("Conferma repository di INPUT", default_in_repo)

        # STEP 4: repo output
        out_repo = _ask_path("Conferma repository di OUTPUT", default_out_repo)
        out_repo.mkdir(parents=True, exist_ok=True)

        # STEP 5: scegli file KPI_ (obbligatorio)
        in_file = _pick_file_interactive(in_repo, prefix="KPI_")
        print(f"\n[INFO] Input selezionato: {in_file.name}")

        # load CSV (mantieni prudente: dtype=str)
        df = pd.read_csv(in_file, sep=";", low_memory=False)

        # Normalizza TUTTE le colonne KPI_* in numerico (comma->dot)
        kpi_cols = [c for c in df.columns if c.startswith("KPI_")]
        for c in kpi_cols:
            s = df[c].astype(str).str.replace(",", ".", regex=False)
            df[c] = pd.to_numeric(s, errors="coerce")

        # Normalizza numerici base (comma->dot) se presenti
        for c in ("open", "high", "low", "close", "volume"):
            if c in df.columns:
                s = df[c].astype(str).str.replace(",", ".", regex=False)
                df[c] = pd.to_numeric(s, errors="coerce")

        try:
            # Applica filtro
            print(f"[INFO] Applico filtro regime: {regime_module}")
            df2 = apply_fn(df)
            break

        except Exception as ex:
            print()
            print("❌❌❌  ERRORE APPLICAZIONE FILTRO REGIME  ❌❌❌")
            print(f"Filtro selezionato: {regime_module}")
            print(f"Dettaglio: {type(ex).__name__}: {ex}")
            print()
            print("La scelta del filtro di regime non è valida o il filtro non è applicabile.")
            print("Ripropongo la selezione del filtro di regime.")
            print()
            continue

    def _num_safe(s: pd.Series) -> pd.Series:
        """
        Parse robusto:
        - se numerico -> float
        - se stringa con sola virgola -> converte virgola in punto
        - se già con punto -> non tocca (assume punto decimale)
        """
        if pd.api.types.is_numeric_dtype(s):
            return s.astype("float64")
        x = s.astype(str).str.strip()
        only_comma = x.str.contains(",", na=False) & ~x.str.contains(r"\.", regex=True, na=False)
        x.loc[only_comma] = x.loc[only_comma].str.replace(",", ".", regex=False)
        return pd.to_numeric(x, errors="coerce")

    def _fmt_eu(v: float) -> str:
        if pd.isna(v):
            return "NaN"
        # EU: virgola decimale, nessun separatore migliaia
        return f"{v:.6g}".replace(".", ",")

    for c in ["KPI_ADX_14", "KPI_ATR_PCT_14", "KPI_EMA_21", "KPI_EMA_50", "KPI_EMA_200"]:
        if c in df2.columns:
            s = _num_safe(df2[c])
            nanp = s.isna().mean() * 100.0
            vmin = s.min()
            vmax = s.max()
            q50 = s.quantile(0.5)
            print(
                f"[DBG][KPI_EU] {c}: NaN%={_fmt_eu(nanp)}  min={_fmt_eu(vmin)}  p50={_fmt_eu(q50)}  max={_fmt_eu(vmax)}"
            )
        else:
            print(f"[DBG][KPI_EU] {c}: MISSING")

    # ------------------------------------------------------------
    # ANSI COLORS (terminal output)
    # ------------------------------------------------------------
    class _C:
        RESET = "\033[0m"
        RED = "\033[31m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        CYAN = "\033[36m"
        BOLD = "\033[1m"

    def _ansi(s: str, color: str) -> str:
        return f"{color}{s}{_C.RESET}"

    def _ok_bad(s: str) -> str:
        s2 = str(s).upper().strip()
        if s2 == "OK":
            return _ansi(s, _C.GREEN)
        if s2 == "BAD":
            return _ansi(s, _C.RED)
        return s

    def _level_colored(msg: str, level: str) -> str:
        lvl = str(level).upper().strip()
        if lvl == "A":
            return _ansi(msg, _C.GREEN)
        if lvl == "B":
            return _ansi(msg, _C.YELLOW)
        if lvl == "C":
            return _ansi(msg, _C.RED)
        return msg
    # ------------------------------------------------------------
    # DEBUG RAW: stampa stringhe così come sono nel CSV (no conversion)
    # ------------------------------------------------------------
    for c in ["KPI_ADX_14", "KPI_ATR_PCT_14", "KPI_EMA_21"]:
        if c in df.columns:
            print(f"[DBG][RAW] {c} head:", df[c].astype(str).head(5).tolist())

    # ------------------------------------------------------------
    # DEBUG KPI reali (NaN% + min/max) per capire UNKNOWN=100%
    # ------------------------------------------------------------

    def _to_float_mixed(series: pd.Series) -> pd.Series:
        s = series.astype(str).str.strip()

        # normalizza vuoti / nan string
        s = s.replace({"": None, "None": None, "nan": None, "NaN": None})

        # se contiene sia '.' che ',' assumiamo che l'ultimo simbolo sia il separatore decimale
        # - EU: 1.234,56  -> decimale ','  -> rimuovo '.' e cambio ','->'.'
        # - US: 1,234.56  -> decimale '.'  -> rimuovo ',' (migliaia)
        has_dot = s.str.contains(r"\.", na=False)
        has_comma = s.str.contains(r",", na=False)
        both = has_dot & has_comma

        s_both = s.where(both)

        # posizione dell'ultimo '.' e dell'ultima ','
        last_dot = s_both.str.rfind(".")
        last_comma = s_both.str.rfind(",")

        eu_mask = both & (last_comma > last_dot)  # es: 1.234,56
        us_mask = both & (last_dot > last_comma)  # es: 1,234.56

        # EU case
        s = s.mask(eu_mask, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
        # US case
        s = s.mask(us_mask, s.str.replace(",", "", regex=False))

        # solo virgola -> decimale EU
        only_comma = has_comma & ~has_dot
        s = s.mask(only_comma, s.str.replace(",", ".", regex=False))

        # solo punto -> già ok (decimale US) -> non toccare

        return pd.to_numeric(s, errors="coerce")


    kpi_check = ["KPI_ADX_14", "KPI_ATR_PCT_14", "KPI_EMA_21", "KPI_EMA_50", "KPI_EMA_200"]
    for c in kpi_check:
        if c in df2.columns:
            s = df2[c]
            # prova conversione EU->float per diagnostica
            s_num = _to_float_mixed(s)

            raw_sample = s.dropna().astype(str).head(3).tolist()
            num_sample = s_num.dropna().head(3).tolist()
            print(f"[DBG][KPI][SAMPLE] {c}: raw={raw_sample} -> num={num_sample}")


            print(f"[DBG][KPI] {c}: NaN%={s_num.isna().mean() * 100:.2f}  min={s_num.min()}  max={s_num.max()}")
        else:
            print(f"[DBG][KPI] {c}: MISSING")

    # ------------------------------------------------------------
    # DEBUG REGIME1 - motivo UNKNOWN
    # ------------------------------------------------------------
    if "REGIME_L1_REASON" in df2.columns:
        vc = df2["REGIME_L1_REASON"].astype(str).value_counts().head(5)
        print("[DBG] REGIME_L1_REASON top:", vc.to_dict())

    if "REGIME_L1" in df2.columns:
        pct_unknown = (df2["REGIME_L1"].astype(str).str.upper() == "UNKNOWN").mean() * 100
        print(f"[DBG] UNKNOWN % = {pct_unknown:.2f}")

    # prova a diagnosticare KPI chiave (nomi più probabili)
    candidates = [
        # EMA usate per direzione trend
        "KPI_EMA_21", "KPI_EMA_50", "KPI_EMA_200",

        # KPI regime (nomi reali in suite)
        "KPI_ADX_14",
        "KPI_ATR_PCT_14",
    ]
    bb_candidates = [
        "KPI_BB_WIDTH_PCT",  # usato dal classifier se presente
        "KPI_BB_WIDTH_20_2p0",  # tuo standard KPILIST
        "KPI_BB_WIDTH_20",
        "KPI_BB_WIDTH",
        "BB_WIDTH",
    ]
    all_candidates = candidates + bb_candidates

    present = [c for c in all_candidates if c in df2.columns]
    missing_all = [c for c in all_candidates if c not in df2.columns]

    # separa missing BB da missing "veri"
    bb_missing = [c for c in bb_candidates if c not in df2.columns]
    missing_non_bb = [c for c in missing_all if c not in bb_candidates]

    bb_optional = []
    if bb_missing and ("close" in df2.columns):
        # Se abbiamo close, il classifier può calcolare BB width pct in fallback
        bb_optional = bb_missing
        bb_missing = []

    missing_final = missing_non_bb + bb_missing

    print(f"[DBG][REGIME] KPI candidates present: {present}")
    print(f"[DBG][REGIME] KPI candidates missing: {missing_final}")
    if bb_optional:
        print(f"[DBG][REGIME] BB width optional (computed from close): {bb_optional}")
    for c in present:
        na_rate = float(df2[c].isna().mean() * 100.0)
        print(f"[DBG][REGIME] {c} NaN% = {na_rate:.2f}")

    # ------------------------------------------------------------
    # EXTRA DEBUG REGIME1 (1H): tassi condizioni + quantili
    # Coerente con regime_classifier_1.py:
    # - VOLATILE: atrp >= atr_volatile_enter AND adx < adx_trend_enter
    # - TREND   : adx >= adx_trend_enter (+ EMA alignment)
    # - RANGE   : adx < adx_range_enter AND atrp >= atr_range_enter AND bb_width_pct >= bb_width_range_enter
    # BB width pct: usa KPI_BB_WIDTH_PCT se presente, altrimenti calcola da close (bb_period/bb_k)
    # ------------------------------------------------------------
    def _num(col: str) -> pd.Series:
        if col not in df2.columns:
            return pd.Series([np.nan] * len(df2), index=df2.index)
        return pd.to_numeric(df2[col], errors="coerce")

    def _fmt_eu(x: float, nd: int = 6) -> str:
        try:
            return f"{float(x):.{nd}f}".replace(".", ",")
        except Exception:
            return "nan"

    # serie base
    adx = _num("KPI_ADX_14")
    atrp = _num("KPI_ATR_PCT_14")

    # parametri (prendo quelli del CSV override se disponibili nel contesto, altrimenti fallback)
    # NOTA: qui uso i default già noti dal tuo log; se nel wizard hai un dict cfg/overrides, sostituisci sotto.
    try:
        adx_trend_enter_v = float(adx_trend_enter)
        adx_range_enter_v = float(adx_range_enter)
        atr_volatile_enter_v = float(atr_volatile_enter)
        atr_range_enter_v = float(atr_range_enter)
        bb_width_range_enter_v = float(bb_width_range_enter)
        bb_period_v = int(bb_period)
        bb_k_v = float(bb_k)
    except Exception:
        # fallback hard (coerente coi tuoi override attuali)
        adx_trend_enter_v = 30.0
        adx_range_enter_v = 35.0
        atr_volatile_enter_v = 0.21
        atr_range_enter_v = 0.13
        bb_width_range_enter_v = 0.35
        bb_period_v = 20
        bb_k_v = 2.0

    # BB width pct coerente col classifier
    if "KPI_BB_WIDTH_PCT" in df2.columns:
        bb_width_pct = _num("KPI_BB_WIDTH_PCT")
        bb_src = "KPI_BB_WIDTH_PCT"
    else:
        close = _num("close")
        mid = close.rolling(bb_period_v, min_periods=bb_period_v).mean()
        std = close.rolling(bb_period_v, min_periods=bb_period_v).std(ddof=0)
        upper = mid + (bb_k_v * std)
        lower = mid - (bb_k_v * std)
        bb_width_pct = ((upper - lower) / mid) * 100.0
        bb_src = f"close->BB_WIDTH_PCT(p={bb_period_v},k={bb_k_v})"

    # tassi condizioni (solo su righe dove KPI sono disponibili)
    valid = adx.notna() & atrp.notna() & bb_width_pct.notna()
    n_valid = int(valid.sum())
    if n_valid > 0:
        m_vol = valid & (atrp >= atr_volatile_enter_v) & (adx < adx_trend_enter_v)
        m_trend = valid & (adx >= adx_trend_enter_v)
        m_range = valid & (adx < adx_range_enter_v) & (atrp >= atr_range_enter_v) & (bb_width_pct >= bb_width_range_enter_v)

        print("\n[DBG][REGIME1][RATES] (su righe valide KPI: n=%d)  bb_src=%s" % (n_valid, bb_src))
        print("[DBG][REGIME1][RATES] P(ATR_PCT>=atr_volatile_enter & ADX<adx_trend_enter) = %.2f%%" % (m_vol.sum() / n_valid * 100.0))
        print("[DBG][REGIME1][RATES] P(ADX>=adx_trend_enter) = %.2f%%" % (m_trend.sum() / n_valid * 100.0))
        print("[DBG][REGIME1][RATES] P(RANGE core: ADX<adx_range_enter & ATR_PCT>=atr_range_enter & BBW>=bb_width_range_enter) = %.2f%%" % (m_range.sum() / n_valid * 100.0))

        # quantili utili (min / p50 / p75 / max) per calibrare soglie
        def _q(s: pd.Series):
            s2 = s[valid].astype(float)
            return float(s2.min()), float(s2.quantile(0.50)), float(s2.quantile(0.75)), float(s2.max())

        adx_min, adx_p50, adx_p75, adx_max = _q(adx)
        atr_min, atr_p50, atr_p75, atr_max = _q(atrp)
        bbw_min, bbw_p50, bbw_p75, bbw_max = _q(bb_width_pct)

        print("[DBG][REGIME1][Q] ADX_14      min=%s p50=%s p75=%s max=%s" % (_fmt_eu(adx_min,4), _fmt_eu(adx_p50,4), _fmt_eu(adx_p75,4), _fmt_eu(adx_max,4)))
        print("[DBG][REGIME1][Q] ATR_PCT_14  min=%s p50=%s p75=%s max=%s" % (_fmt_eu(atr_min,6), _fmt_eu(atr_p50,6), _fmt_eu(atr_p75,6), _fmt_eu(atr_max,6)))
        print("[DBG][REGIME1][Q] BBW_PCT     min=%s p50=%s p75=%s max=%s  (src=%s)" % (_fmt_eu(bbw_min,6), _fmt_eu(bbw_p50,6), _fmt_eu(bbw_p75,6), _fmt_eu(bbw_max,6), bb_src))
    else:
        print("\n[DBG][REGIME1][RATES] n_valid=0 (KPI insufficient: ADX/ATR/BBW)")





    # STEP 6: genera report
    build_regime_report, write_single_csv_report = _import_report_tools(suite_root)

    print("[INFO] Genero report filtro (CSV singolo)...")

    # ------------------------------------------------------------
    # ALLOW_TRADE (per report impatto: righe inibite)
    # Default tuning: consideriamo "ammesso" tutto ciò che NON è UNKNOWN
    # ------------------------------------------------------------
    if "REGIME_L1" in df2.columns:
        sreg = df2["REGIME_L1"].astype(str).str.strip().str.upper()
        df2["ALLOW_TRADE"] = (~sreg.eq("UNKNOWN")).astype(int)
    else:
        # fallback: nessun regime => tutto ammesso
        df2["ALLOW_TRADE"] = 1

    sheets = build_regime_report(df2, regime_col="REGIME_L1")

    # ------------------------------------------------------------
    # WIZARD OUTPUT: Impatto filtro (righe inibite) da DATASET_SUMMARY
    # ------------------------------------------------------------
    ds = sheets.get("DATASET_SUMMARY")
    if ds is not None and not getattr(ds, "empty", True):
        cols = [c.lower().strip() for c in ds.columns.astype(str)]
        # supporta sia schema (metric,value) che varianti
        if "metric" in cols and "value" in cols:
            mcol = ds.columns[cols.index("metric")]
            vcol = ds.columns[cols.index("value")]
            dsv = {str(k).strip(): str(v).strip() for k, v in zip(ds[mcol], ds[vcol])}

            # prova a trovare i campi più tipici
            keys_try = [
                "rows_total", "rows_allowed", "rows_blocked",
                "blocked_rows", "inhibited_rows",
                "pct_blocked", "blocked_pct", "inhibited_pct",
            ]

            print("\n===== REGIME FILTER IMPACT =====")
            found_any = False
            for k in keys_try:
                if k in dsv:
                    print(f"{k}: {dsv[k]}")
                    found_any = True

            # fallback: stampa tutte le metriche che contengono blocked/inib/allow/total
            if not found_any:
                for k, v in dsv.items():
                    lk = k.lower()
                    if any(t in lk for t in ("blocked", "inib", "allow", "total")):
                        print(f"{k}: {v}")



    # ------------------------------------------------------------
    # WIZARD OUTPUT: Coverage vs Target (include regimi a 0%)
    # ------------------------------------------------------------
    coverage_pct = _extract_regime_coverage_pct_from_sheets(sheets, regime_col="REGIME_L1")




    def _infer_timeframe_label_from_filename(path_str: str) -> str:
        s = (path_str or "").lower()
        if "_30min_" in s or "_30m_" in s or "30min" in s:
            return "30m"
        if "_1hour_" in s or "_1h_" in s or "1hour" in s:
            return "1h"
        if "_1day_" in s or "_1d_" in s or "1day" in s:
            return "1d"
        if "_1week_" in s or "_1w_" in s or "1week" in s:
            return "1w"
        return "unknown"

    # timeframe label coerente con il file input selezionato
    # (usa la variabile path già disponibile nel tuo blocco; se è una Path, va bene str(path))

    # target set per timeframe (se non esistono i target dedicati, fallback a 30m)
    timeframe_label = _infer_timeframe_label_from_filename(str(in_file))
    # targets timeframe-aware (con fallback + warning)
    targets_fallback_warn = None
    targets = get_regime_l1_targets(timeframe_label)
    tf_map = globals().get("REGIME_L1_TARGETS_BY_TF", {})
    if not isinstance(tf_map, dict) or timeframe_label not in tf_map:
        targets_fallback_warn = (
            f"[REGIME][WARN] Target band specifici per timeframe '{timeframe_label}' non trovati: "
            "uso REGIME_L1_TARGETS (fallback)."
        )


        # ------------------------------------------------------------
        # WIZARD OUTPUT: Validazione statistica (Kruskal/Chi2 ecc.)
        # + aggiunta al CSV come sezione "REGIME_VALIDATION_STATS"
        # ------------------------------------------------------------

    # ------------------------------------------------------------
    # STATS SHEET (serve al report centralizzato)
    # ------------------------------------------------------------
    stats_sheet = _build_regime_validation_stats_sheet(
        df2,
        regime_col="REGIME_L1",
        coverage_pct=coverage_pct,
        targets=targets,
    )

    _validation = print_regime_wizard_report(
        df2,
        timeframe_label=timeframe_label,
        targets=targets,
        stats_sheet=stats_sheet,
        targets_fallback_warn=targets_fallback_warn,
        show_verdict=True,
    )

    # stampa compatta a video (metric/value)
    #if stats_sheet is not None and not stats_sheet.empty:
    #    for _, r in stats_sheet.iterrows():
     #       print(f"{r['metric']}: {r['value']}")
    #else:
     #   print("stats_available: NO (empty sheet)")

    # aggiungi al report CSV singolo (nuova sezione)
    sheets["REGIME_VALIDATION_STATS"] = stats_sheet



    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # Salva anche il CSV operativo post-regime per Run_strategia
    # Formato coerente con la suite:
    # - separatore colonne = ;
    # - decimale = ,
    # ------------------------------------------------------------
    out_data_path = build_regime_output_path(in_file)
    df2.to_csv(
        out_data_path,
        sep=";",
        decimal=",",
        index=False,
        encoding="utf-8-sig",
    )

    # ------------------------------------------------------------
    # Salva il report CSV regime
    # ------------------------------------------------------------
    out_name = f"REGIME_REPORT_{in_file.stem}.csv"
    out_path = out_repo / out_name

    write_single_csv_report(out_path, sheets)

    print(f"[OK] File dati post-regime scritto: {out_data_path}")
    print("[OK] Formato file dati post-regime: sep=';' decimal=',' encoding='utf-8-sig'")
    print(f"[OK] Report scritto: {out_path}")
    return 0


def _debug_python_env():
    import sys
    print("\n[DEBUG][PYTHON ENV]")
    print("sys.executable:", sys.executable)
    print("sys.version:", sys.version)
    try:
        import scipy
        print("[DEBUG] scipy OK:", scipy.__version__)
        print("[DEBUG] scipy file:", scipy.__file__)
    except Exception as e:
        print("[DEBUG] scipy IMPORT FAIL:", repr(e))
    print()

if __name__ == "__main__":
    _debug_python_env()
    raise SystemExit(main())
