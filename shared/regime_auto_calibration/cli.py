# Py_SUITE_TRADING/shared/regime_auto_calibration/cli.py
import argparse
from pathlib import Path
import io
import sys
import pandas as pd
import numpy as np
import re
import shutil
import csv


from .engine import run_calibration


def _read_report_sections(report_path: str | Path) -> dict[str, pd.DataFrame]:
    """
    Legge un report CSV multi-sezione (formato: linee '### SHEET=NAME')
    e restituisce un dict: {section_name: DataFrame}.

    Robustezza:
    - prova prima sep=';' (EU-friendly) poi sep=','
    - usa engine='python' per tollerare righe irregolari
    - ignora righe vuote
    """
    text = Path(report_path).read_text(encoding="utf-8", errors="ignore").splitlines()

    sections: dict[str, list[str]] = {}
    current = None

    for line in text:
        s = line.strip()
        if not s:
            continue
        if s.startswith("###") and "SHEET=" in s:
            # es: ### SHEET=DATASET_SUMMARY
            current = s.split("SHEET=", 1)[1].strip()
            sections[current] = []
            continue
        if current is None:
            # prima sezione non dichiarata: la scartiamo
            continue
        sections[current].append(line)

    out: dict[str, pd.DataFrame] = {}

    for name, lines in sections.items():
        buf = "\n".join(lines).strip()
        if not buf:
            continue

        # Prova separatore ';' poi ','
        last_err = None
        for sep in (";", ","):
            try:
                df = pd.read_csv(
                    io.StringIO(buf),
                    sep=sep,
                    engine="python",
                )
                out[name] = df
                last_err = None
                break
            except Exception as e:
                last_err = e

        if last_err is not None:
            # fallback estremo: prova a saltare righe problematiche
            try:
                df = pd.read_csv(
                    io.StringIO(buf),
                    sep=";",
                    engine="python",
                    on_bad_lines="skip",
                )
                out[name] = df
            except Exception:
                # se proprio non si riesce, non bloccare tutto
                out[name] = pd.DataFrame()

    return out

def _print_wizard_style_from_report(report_csv: Path) -> None:
    """
    Fallback robusto: stampa una sintesi "wizard-style" direttamente dal report multi-sezione
    (### SHEET=...), evitando parse fragile nel wizard.
    """
    print("\n===== REGIME REPORT (wizard-style fallback) =====")
    print(f"[INFO] report: {report_csv}")

    sections = _read_report_sections(report_csv)

    # 1) DATASET_SUMMARY
    ds = sections.get("DATASET_SUMMARY")
    if ds is not None and not ds.empty:
        print("\n-- DATASET SUMMARY --")
        cols = [str(c).strip().lower() for c in ds.columns]
        if "metric" in cols and "value" in cols:
            for _, r in ds.iterrows():
                m = str(r.get("metric", "")).strip()
                v = str(r.get("value", "")).strip()
                if m:
                    print(f"{m:25s} | {v}")
        else:
            print(ds.head(60).to_string(index=False))
    else:
        print("\n[WARN] sezione DATASET_SUMMARY mancante o vuota.")

    # 2) REGIME_COVERAGE
    cov = sections.get("REGIME_COVERAGE")
    if cov is not None and not cov.empty:
        print("\n-- REGIME COVERAGE --")
        print(cov.head(80).to_string(index=False))
    else:
        print("\n[WARN] sezione REGIME_COVERAGE mancante o vuota.")

    # 3) opzionale: STATS / STATISTICS
    st = sections.get("STATS") or sections.get("STATISTICS")
    if st is not None and not st.empty:
        print("\n-- STATS --")
        cols = [str(c).strip().lower() for c in st.columns]
        if "metric" in cols and "value" in cols:
            for _, r in st.iterrows():
                m = str(r.get("metric", "")).strip()
                v = str(r.get("value", "")).strip()
                if m:
                    print(f"{m:25s} | {v}")
        else:
            print(st.head(80).to_string(index=False))

def _read_report_sheets(report_csv: Path) -> dict[str, list[str]]:
    """
    Legge il report CSV nel formato:
      ### SHEET=NAME
      ...righe...
    e ritorna dict {sheet_name: [righe]} (senza header sheet).
    """
    sheets: dict[str, list[str]] = {}
    cur = None
    for raw in report_csv.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if line.startswith("### SHEET="):
            cur = line.split("=", 1)[1].strip()
            sheets[cur] = []
            continue
        if cur is not None:
            sheets[cur].append(line)
    return sheets


def _print_sheet_block(title: str, lines: list[str], *, max_lines: int | None = None) -> None:
    print(f"\n===== {title} =====")
    if not lines:
        print("(vuoto)")
        return
    if max_lines is None:
        for l in lines:
            print(l)
    else:
        for l in lines[:max_lines]:
            print(l)
        if len(lines) > max_lines:
            print(f"... ({len(lines) - max_lines} righe omesse)")


def print_wizard_style_stats_from_report(report_csv: str) -> None:
    """
    Stampa a console i blocchi principali del report, stile wizard.
    """
    p = Path(report_csv)
    if not p.exists():
        print(f"\n[WARN] Best report non trovato: {p}")
        return

    sheets = _read_report_sheets(p)

    # 1) Dataset summary
    for key in ("DATASET_SUMMARY", "DATASET", "SUMMARY"):
        if key in sheets:
            _print_sheet_block(key, sheets[key])
            break

    # 2) Regime coverage
    for key in ("REGIME_COVERAGE", "COVERAGE", "REGIME_TABLE"):
        if key in sheets:
            _print_sheet_block(key, sheets[key])
            break

    # 3) Stats / tests (chi2 / kruskal / cliff / spread)
    for key in ("STATS", "STATS_SHEET", "STATISTICS", "VALIDATION_STATS"):
        if key in sheets:
            _print_sheet_block(key, sheets[key])
            break

    # 4) (opzionale) Verdict se presente come sheet
    for key in ("VERDICT", "VALIDATION_VERDICT"):
        if key in sheets:
            _print_sheet_block(key, sheets[key])
            break


def print_observed_vs_target_from_report(report_csv: str | Path, timeframe: str = "1d") -> None:
    """
    Stampa solo la parte:
      - [REGIME][TARGET]
      - [REGIME][TABLE] Coverage osservata vs target
      - [REGIME][STATUS]
    Partendo dal report CSV multi-sezione (SHEET=REGIME_COVERAGE).
    NON ri-applica il regime (evita mismatch signature apply_regime_L1).
    """
    p = Path(report_csv)
    if not p.exists():
        print(f"\n[WARN] report non trovato: {p}")
        return

    sheets = _read_report_sheets(p)
    lines = sheets.get("REGIME_COVERAGE") or []
    # cerca header + riga 'share'
    header = None
    row_share = None
    for line in lines:
        if not line.strip():
            continue
        if header is None and ";" in line and not line.lower().startswith("bars;") and not line.lower().startswith("share;"):
            header = [x.strip() for x in line.split(";")]
            continue
        if line.lower().startswith("share;"):
            row_share = [x.strip() for x in line.split(";")]
            break

    if not header or not row_share or len(header) != len(row_share):
        # report non conforme o incompleto
        return

    share_pct: dict[str, float] = {}
    for col, v in zip(header[1:], row_share[1:]):
        try:
            share_pct[col] = float(v) * 100.0
        except Exception:
            share_pct[col] = 0.0

    # costruisci coverage canonico
    cov: dict[str, float] = {}
    # usa TREND se presente, altrimenti somma TREND_UP/DOWN
    if "TREND" in share_pct:
        cov["TREND"] = share_pct.get("TREND", 0.0)
    else:
        cov["TREND"] = share_pct.get("TREND_UP", 0.0) + share_pct.get("TREND_DOWN", 0.0)

    for k in ("RANGE", "LATERAL", "VOLATILE", "UNKNOWN", "TREND_UP", "TREND_DOWN"):
        cov[k] = share_pct.get(k, 0.0)

    targets, tf_label = _get_targets_for_timeframe(timeframe)

    print(f"\n[REGIME][TARGET] Range di riferimento (timeframe {tf_label}):")
    for k in ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN", "TREND_DOWN", "TREND_UP"]:
        band = targets.get(k)
        if band is None:
            print(f"- {k:11s}: n/a")
        else:
            lo, hi = band
            print(f"- {k:11s}: {lo}% – {hi}%")

    print(f"\n[REGIME][TABLE] Coverage osservata vs target (timeframe {tf_label})")
    print("REGIME       | OBSERVED % |      TARGET % | DELTA to band | STATUS")
    print("------------------------------------------------------------------")

    out_regs: list[str] = []
    for k in ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN", "TREND_DOWN", "TREND_UP"]:
        obs = float(cov.get(k, 0.0) or 0.0)
        band = targets.get(k)
        delta, status = _delta_to_band(obs, band)
        targ_str = "n/a" if band is None else f"{band[0]}–{band[1]}"
        print(f"{k:11s} | {obs:10.2f} | {targ_str:11s} | {delta:12.2f} | {status:5s}")
        if status == "OUT":
            out_regs.append(k)

    if out_regs:
        print("\n[REGIME][STATUS] ⚠ CALIBRAZIONE NECESSARIA")
        print(f"[REGIME][DETAIL] Regimi fuori target: {', '.join(out_regs)}")
    else:
        print("\n[REGIME][STATUS] ✅ COVERAGE IN TARGET")
# ----------------------------
# Wizard-style final print
# ----------------------------

def _fmt_eu(x, nd=6) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, (int, np.integer)):
            return str(int(x))
        fx = float(x)
    except Exception:
        return str(x)
    if np.isnan(fx):
        return "NaN"
    s = f"{fx:.{nd}f}"
    return s.replace(".", ",")

def _c(s: str, color: str) -> str:
    """
    Colorazione ANSI leggera per CLI. Si attiva solo su TTY.
    color: 'red'|'green'|'yellow'|'cyan'|'gray'|'bold'|None
    """
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return s
    codes = {
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
        "gray": "\033[90m",
        "bold": "\033[1m",
        None: "",
        "": "",
    }
    reset = "\033[0m"
    return f"{codes.get(color,'')}{s}{reset}" if color else s

def _params_from_config_csv(cfg_csv: Path) -> dict:
    """
    Legge param/value da CSV (supporta ';' o ',') e ritorna dict.
    Accetta valori EU con virgola.
    """
    import csv

    txt = cfg_csv.read_text(encoding="utf-8-sig").splitlines()
    if not txt:
        return {}
    first = txt[0]
    delim = ";" if first.count(";") >= first.count(",") else ","

    out = {}
    with cfg_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim, skipinitialspace=True)
        if not reader.fieldnames:
            return out
        hdr = [h.strip().lower() for h in reader.fieldnames]
        key_col = "param" if "param" in hdr else ("key" if "key" in hdr else None)
        val_col = "value" if "value" in hdr else None
        if key_col is None or val_col is None:
            raise ValueError(f"[CLI] schema config non riconosciuto: {reader.fieldnames}")

        # map original header -> normalized
        hmap = {h: h.strip().lower() for h in reader.fieldnames}

        for r in reader:
            rr = {hmap.get(k, k): v for k, v in r.items()}
            k = rr.get(key_col)
            v = rr.get(val_col)
            if k is None:
                continue
            k = str(k).strip()
            if not k:
                continue
            v = "" if v is None else str(v).strip()
            if v == "":
                continue

            # numeric parse (EU comma)
            try:
                fv = float(v.replace(".", "").replace(",", ".") if (v.count(".") >= 2 and "," not in v) else v.replace(",", "."))
                out[k] = fv
            except Exception:
                out[k] = v
    return out


def _get_targets_for_timeframe(timeframe: str):
    """
    Ritorna (targets, timeframe_label).
    - 1d: VOLATILE può essere 0% (banda 0–20)
    - fallback: 30m (VOLATILE 5–20) con WARN
    Robustezza: timeframe può arrivare non-string (es. dict) da call-site esterni.
    """
    REGIME_L1_TARGETS_30M = {
        "TREND": (25, 45),
        "RANGE": (30, 55),
        "LATERAL": (30, 55),
        "VOLATILE": (5, 20),
        "UNKNOWN": (0, 0),
        "TREND_DOWN": None,
        "TREND_UP": None,
    }

    REGIME_L1_TARGETS_1D = {
        "TREND": (25, 45),
        "RANGE": (30, 55),
        "LATERAL": (30, 55),
        "VOLATILE": (0, 20),
        "UNKNOWN": (0, 0),
        "TREND_DOWN": None,
        "TREND_UP": None,
    }

    # timeframe può arrivare come dict: tenta estrazione
    tf_obj = timeframe
    if isinstance(tf_obj, dict):
        for k in ("timeframe", "timeframe_label", "tf", "label", "value"):
            v = tf_obj.get(k)
            if isinstance(v, str) and v.strip():
                tf_obj = v
                break

    tf = str(tf_obj or "").strip().lower()
    if tf in ("1d", "1day", "day", "daily"):
        return REGIME_L1_TARGETS_1D, "1d"

    # fallback
    tf_label = tf if tf else "unknown"
    print(f"[REGIME][WARN] Target band specifici per timeframe '{tf_label}' non trovati: uso REGIME_L1_TARGETS_30M (fallback).")
    return REGIME_L1_TARGETS_30M, tf_label




def _coverage_from_regime(df: pd.DataFrame, regime_col: str = "REGIME_L1") -> dict:
    reg = (
        df[regime_col]
        .astype(str)
        .fillna("")
        .str.strip()
        .str.upper()
    )
    vc = reg.value_counts(dropna=False)
    total = float(vc.sum()) if len(vc) else 0.0

    def pct(name):
        return (float(vc.get(name, 0)) / total * 100.0) if total > 0 else 0.0

    out = {
        "TREND_UP": pct("TREND_UP"),
        "TREND_DOWN": pct("TREND_DOWN"),
        "RANGE": pct("RANGE"),
        "LATERAL": pct("LATERAL"),
        "VOLATILE": pct("VOLATILE"),
        "UNKNOWN": pct("UNKNOWN"),
    }
    out["TREND"] = out["TREND_UP"] + out["TREND_DOWN"]
    return out


def _delta_to_band(obs: float, band) -> tuple[float, str]:
    if band is None:
        return 0.0, "N/A"
    lo, hi = band
    if obs < lo:
        return float(lo - obs), "OUT"
    if obs > hi:
        return float(obs - hi), "OUT"
    return 0.0, "IN"


def _forward_returns(df: pd.DataFrame, close_col: str = "close") -> pd.DataFrame:
    out = df.copy()
    c = pd.to_numeric(out[close_col], errors="coerce")
    if "r1" not in out.columns:
        out["r1"] = (c.shift(-1) / c) - 1.0
    if "r5" not in out.columns:
        out["r5"] = (c.shift(-5) / c) - 1.0
    return out


def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a)
    b = np.asarray(b)
    gt = 0
    lt = 0
    for x in a:
        gt += int((x > b).sum())
        lt += int((x < b).sum())
    denom = a.size * b.size
    return (gt - lt) / denom if denom else np.nan


def print_wizard_style_summary(*, input_csv: Path, best_config_csv: Path, timeframe: str = "1d") -> None:
    """
    Stampa finale in stile wizard:
    - REGIME FILTER IMPACT
    - TARGET bands + coverage table + status
    - VALIDATION STATS (chi2/kruskal)
    - VERDICT (AUTO + spiegazione)
    - Summary by Regime (PRO) + Top/Bottom
    """
    import importlib

    # Lettura robusta: prima EU ';', poi fallback ','
    try:
        df0 = pd.read_csv(input_csv, sep=";", low_memory=False)
    except Exception:
        df0 = pd.read_csv(input_csv, sep=",", low_memory=False)


    core = importlib.import_module("shared.regime_classifier_1")

    params = _params_from_config_csv(best_config_csv)

    # Applica regime (core)
    # Firma compatibile: usa posizionale per evitare mismatch kwargs
    df_r = core.apply_regime_L1(df0.copy(), "L1", params)

    regime_col = "REGIME_L1" if "REGIME_L1" in df_r.columns else ("REGIME_L1_RAW" if "REGIME_L1_RAW" in df_r.columns else "REGIME_L1_CODE")

    # ---------------------------
    # REGIME FILTER IMPACT
    # ---------------------------
    rows_total = int(len(df_r))
    rows_allowed = rows_total
    rows_blocked = 0
    pct_blocked = 0.0

    print("\n===== REGIME FILTER IMPACT =====")
    print(f"rows_total: {rows_total}")
    print(f"rows_allowed: {rows_allowed}")
    print(f"rows_blocked: {rows_blocked}")
    print(f"pct_blocked: {_fmt_eu(pct_blocked, nd=1)}")

    # ---------------------------
    # TARGET + COVERAGE TABLE
    # ---------------------------
    targets, tf_label = _get_targets_for_timeframe(timeframe)

    print(f"\n[REGIME][TARGET] Range di riferimento (timeframe {tf_label}):")
    for k in ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN", "TREND_DOWN", "TREND_UP"]:
        band = targets.get(k)
        if band is None:
            print(f"- {k:11s}: n/a")
        else:
            lo, hi = band
            print(f"- {k:11s}: {lo}% – {hi}%")

    cov = _coverage_from_regime(df_r, regime_col=regime_col)

    print(f"\n[REGIME][TABLE] Coverage osservata vs target (timeframe {tf_label})")
    print("REGIME       | OBSERVED % |      TARGET % | DELTA to band | STATUS")
    print("------------------------------------------------------------------")

    out_regs = []
    for k in ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN", "TREND_DOWN", "TREND_UP"]:
        obs = cov.get(k, 0.0)
        band = targets.get(k)
        delta, status = _delta_to_band(obs, band)
        targ_str = "n/a" if band is None else f"{band[0]}–{band[1]}"
        print(f"{k:11s} | {obs:10.2f} | {targ_str:11s} | {delta:12.2f} | {status:5s}")
        if status == "OUT":
            out_regs.append(k)

    if out_regs:
        print("\n[REGIME][STATUS] ⚠ CALIBRAZIONE NECESSARIA")
        print(f"[REGIME][DETAIL] Regimi fuori target: {', '.join(out_regs)}")
    else:
        print("\n[REGIME][STATUS] ✅ COVERAGE IN TARGET")

    # ---------------------------
    # VALIDATION STATS
    # ---------------------------
    print("\n===== REGIME FILTER VALIDATION (STATS) =====")

    # Chi2 vs target midpoints
    try:
        from scipy.stats import chisquare, kruskal
        have_scipy = True
    except Exception:
        have_scipy = False

    # usa chi2 solo su keys con band non None e con obs > 0
    chi2_keys = [k for k in ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN"] if targets.get(k) is not None]
    obs_counts = []
    exp_counts = []
    # conteggi osservati: converti % in counts usando rows_total
    for k in chi2_keys:
        obs_counts.append(cov[k] / 100.0 * rows_total)
        mid = sum(targets[k]) / 2.0
        exp_counts.append(mid / 100.0 * rows_total)

    print("\n-- Chi2 vs Target --")
    print("(Test di aderenza tra distribuzione osservata e midpoint dei target.\n p-value < 0,05 → distribuzione significativamente diversa dal target.)")
    print(f"chi2_target_keys     | {','.join(chi2_keys)}")
    print(f"chi2_total_rows      | {rows_total}")
    print(f"chi2_obs_total_used  | {int(round(sum(obs_counts)))}")

    chi2_stat = np.nan
    chi2_p = np.nan
    if have_scipy and sum(exp_counts) > 0:
        # normalizza exp su somma obs per coerenza
        s_obs = sum(obs_counts)
        s_exp = sum(exp_counts)
        exp_counts = [e * (s_obs / s_exp) for e in exp_counts]
        chi2_stat, chi2_p = chisquare(f_obs=obs_counts, f_exp=exp_counts)
        chi2_stat = float(chi2_stat)
        chi2_p = float(chi2_p)

    print(f"chi2_stat            | {_fmt_eu(chi2_stat, nd=6)}")
    print(f"chi2_pvalue          | {_fmt_eu(chi2_p, nd=6)}")

    # Kruskal (r1/r5) su regimi con n>=min_n
    df_ret = _forward_returns(df_r, close_col="close")
    min_n = 30
    regimes = (
        df_ret[regime_col].astype(str).str.strip().str.upper()
        if regime_col in df_ret.columns else pd.Series([], dtype=str)
    )

    def _groups_for(col):
        groups = {}
        for r in ["LATERAL", "RANGE", "TREND_UP", "TREND_DOWN", "VOLATILE", "UNKNOWN"]:
            x = pd.to_numeric(df_ret.loc[regimes == r, col], errors="coerce").dropna().values
            if len(x) >= min_n:
                groups[r] = x
        return groups

    g1 = _groups_for("r1")
    g5 = _groups_for("r5")

    print("\n-- Kruskal Tests --")
    print("(Test non parametrico di differenza tra regimi sui forward returns.\n p-value < 0,05 → almeno un regime differisce in modo significativo.)")
    print(f"kruskal_min_n_per_group | {min_n}")

    def _kruskal_line(name, groups):
        if not have_scipy or len(groups) < 2:
            return np.nan, np.nan, ""
        stat, p = kruskal(*[groups[k] for k in groups.keys()])
        return float(stat), float(p), ",".join(groups.keys())

    stat1, p1, keys1 = _kruskal_line("r1", g1)
    stat5, p5, keys5 = _kruskal_line("r5", g5)

    print(f"kruskal_r1_groups    | {keys1}")
    print(f"kruskal_r1_stat      | {_fmt_eu(stat1, nd=6)}")
    print(f"kruskal_r1_pvalue    | {_fmt_eu(p1, nd=6)}")
    print(f"kruskal_r5_groups    | {keys5}")
    print(f"kruskal_r5_stat      | {_fmt_eu(stat5, nd=6)}")
    print(f"kruskal_r5_pvalue    | {_fmt_eu(p5, nd=6)}")

    # Effect size (max abs cliff on r5) + spread r5 mean
    means = {}
    for r in ["LATERAL", "RANGE", "TREND_UP", "TREND_DOWN", "VOLATILE", "UNKNOWN"]:
        x = pd.to_numeric(df_ret.loc[regimes == r, "r5"], errors="coerce").dropna()
        if len(x):
            means[r] = float(x.mean())

    spread = (max(means.values()) - min(means.values())) if len(means) >= 2 else np.nan

    vals = {}
    for r, x in _groups_for("r5").items():
        vals[r] = x
    best_cliff = 0.0
    ks = list(vals.keys())
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            d = _cliffs_delta(vals[ks[i]], vals[ks[j]])
            if not np.isnan(d):
                best_cliff = max(best_cliff, abs(float(d)))

    # ---------------------------
    # VERDICT (AUTO)
    # ---------------------------
    # Soglie (allineate alla logica che usi di solito):
    chi2_ok = (not np.isnan(chi2_p)) and (chi2_p >= 0.05)
    kr_ok = (not np.isnan(p5)) and (p5 < 0.05)
    cliff_ok = (not np.isnan(best_cliff)) and (best_cliff >= 0.147)
    spread_ok = (not np.isnan(spread)) and (spread >= 0.002)

    print("\n===== REGIME VALIDATION VERDICT (AUTO A/B/C) =====")

    level = "A" if (chi2_ok and kr_ok and cliff_ok and spread_ok) else (
        "B" if (kr_ok and cliff_ok and spread_ok) else "C")
    msg = "✅ OK" if level == "A" else ("ℹ️ CALIBRAZIONE RACCOMANDATA" if level == "B" else "⚠️ DA RIVEDERE")

    level_color = "green" if level == "A" else ("yellow" if level == "B" else "red")
    print(f"{_c(msg, level_color)}  (level={_c(level, 'bold')})")

    def _tag(ok: bool) -> str:
        return _c("OK", "green") if ok else _c("BAD", "red")

    print(f"- chi2_pvalue={_fmt_eu(chi2_p, nd=6)} ({_tag(chi2_ok)})")
    print(f"- kruskal_r5_pvalue={_fmt_eu(p5, nd=6)} ({_tag(kr_ok)})")
    print(f"- max|cliff_r5|={_fmt_eu(best_cliff, nd=6)} ({_tag(cliff_ok)})")
    print(f"- spread_r5_mean={_fmt_eu(spread, nd=6)} ({_tag(spread_ok)})")


    print("\n===== REGIME VALIDATION VERDICT =====")
    if not chi2_ok and (kr_ok or cliff_ok or spread_ok):
        print("⚠ Regimi informativi ma coverage fuori target (Chi²)")
        print("  (Differenziazione statistica OK, ma calibrazione distribuzione consigliata)")
        print(f"  kruskal_pvalue_r5: {float(p5) if not np.isnan(p5) else p5}")
        print(f"  max|cliff_r5|: {round(best_cliff, 4) if not np.isnan(best_cliff) else best_cliff}")
        print(f"  spread r5_mean: {round(spread, 6) if not np.isnan(spread) else spread}")
        print("  chi2_pvalue_coverage: < 1e-6" if (not np.isnan(chi2_p) and chi2_p < 1e-6) else f"  chi2_pvalue_coverage: {chi2_p}")
    else:
        print("✅ Verdict coerente con coverage e differenziazione.")

    # ---------------------------
    # Summary by regime (PRO)
    # ---------------------------
    print("\n-- Summary by Regime (PRO) --")
    print("(Statistiche forward return r1/r5 per regime.\n r*_hit = probabilità di rendimento positivo.\n cliff5 = effect size vs miglior regime (range [-1,+1]).)")

    rows = []
    for r in ["LATERAL", "RANGE", "TREND_UP", "TREND_DOWN", "VOLATILE", "UNKNOWN"]:
        sub = df_ret.loc[regimes == r].copy()
        r1 = pd.to_numeric(sub["r1"], errors="coerce").dropna()
        r5 = pd.to_numeric(sub["r5"], errors="coerce").dropna()
        if len(sub) == 0:
            continue
        rows.append({
            "REGIME": r,
            "N": int(len(sub)),
            "r1_mean": float(r1.mean()) if len(r1) else np.nan,
            "r1_med": float(r1.median()) if len(r1) else np.nan,
            "r1_std": float(r1.std(ddof=1)) if len(r1) > 1 else np.nan,
            "r1_hit": float((r1 > 0).mean()) if len(r1) else np.nan,
            "r5_mean": float(r5.mean()) if len(r5) else np.nan,
            "r5_med": float(r5.median()) if len(r5) else np.nan,
            "r5_std": float(r5.std(ddof=1)) if len(r5) > 1 else np.nan,
            "r5_hit": float((r5 > 0).mean()) if len(r5) else np.nan,
            "r5_vals": r5.values,
        })

    # ranking per r5_mean
    rows_sorted = sorted(rows, key=lambda d: (d["r5_mean"] if not np.isnan(d["r5_mean"]) else -1e9), reverse=True)
    best_reg = rows_sorted[0]["REGIME"] if rows_sorted else None
    best_vals = rows_sorted[0]["r5_vals"] if rows_sorted else None

    # stampa tabella
    print("REGIME       |      N |      r1_mean |     r1_med |     r1_std |    r1_hit |      r5_mean |     r5_med |     r5_std |    r5_hit |    cliff5")
    print("-------------------------------------------------------------------------------------------------------------------------------------------")
    for d in rows_sorted:
        cliff5 = np.nan
        if best_reg and d["REGIME"] != best_reg and best_vals is not None and len(best_vals) and len(d["r5_vals"]):
            cliff5 = _cliffs_delta(d["r5_vals"], best_vals)
        star = " ★" if d["REGIME"] == best_reg else ""
        warn = " ⚠" if d["REGIME"] in out_regs else ""
        name = f"{d['REGIME']}{star}{warn}"
        print(f"{name:11s} | {d['N']:6d} | {_fmt_eu(d['r1_mean'],6):>12s} | {_fmt_eu(d['r1_med'],6):>10s} | {_fmt_eu(d['r1_std'],6):>10s} | {_fmt_eu(d['r1_hit'],6):>8s} | {_fmt_eu(d['r5_mean'],6):>12s} | {_fmt_eu(d['r5_med'],6):>10s} | {_fmt_eu(d['r5_std'],6):>10s} | {_fmt_eu(d['r5_hit'],6):>8s} | {_fmt_eu(cliff5,6):>10s}")

    print("(Ranking per rendimento medio a 5 barre forward.)")

    # Top/Bottom
    print("\n-- Top 4 by r5_mean --")
    print("REGIME       |      r5_mean")
    print("----------------------------")
    for d in rows_sorted[:4]:
        print(f"{d['REGIME']:11s} | {_fmt_eu(d['r5_mean'],6):>12s}")

    print("\n-- Bottom 4 by r5_mean --")
    if len(rows_sorted) <= 4:
        print("(non separato: numero regimi troppo basso, coincide con Top)")
    else:
        print("REGIME       |      r5_mean")
        print("----------------------------")
        for d in rows_sorted[-4:]:
            print(f"{d['REGIME']:11s} | {_fmt_eu(d['r5_mean'],6):>12s}")


def _export_wizard_config_from_best_config(
    *,
    best_config_csv: "Path",
    best_dir: "Path",
    symbol: str,
    timeframe: str,
) -> "Path":
    """
    Crea un config CSV wizard-readable dentro best_dir con nome canonico:
      config_filtro_regime_classifier_<SYMBOL>_<TIMEFRAME>.csv

    Sorgente: best_config_csv (param;value;note).
    Non usa il report, perché il report NON contiene i parametri.
    """


    best_config_csv = Path(best_config_csv)
    best_dir = Path(best_dir)
    best_dir.mkdir(parents=True, exist_ok=True)

    required_order = [
        "adx_trend_enter",
        "adx_trend_exit",
        "",
        "adx_range_enter",
        "adx_range_exit",
        "",
        "atr_volatile_enter",
        "atr_volatile_exit",
        "",
        "atr_range_enter",
        "atr_range_exit",
        "",
        "bb_width_range_enter",
        "bb_width_range_exit",
        "",
        "bb_period",
        "bb_k",
        "",
        "confirm_bars_trend",
        "confirm_bars_range",
        "confirm_bars_volatile",
    ]
    required_set = {k for k in required_order if k}

    # --- load source (param;value;note) ---
    rows = []
    with best_config_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            p = (r.get("param") or "").strip()
            v = (r.get("value") or "").strip()
            n = (r.get("note") or "").strip()
            if not p:
                continue
            rows.append({"param": p, "value": v, "note": n})

    m = {r["param"]: r for r in rows}

    missing = sorted(required_set - set(m.keys()))
    if missing:
        raise ValueError(
            "[AUTO_CAL][EXPORT] best_config non contiene tutti i parametri richiesti dal wizard. "
            f"Missing={missing}. Source={best_config_csv}"
        )

    out_name = f"config_filtro_regime_classifier_{symbol}_{timeframe}.csv"
    out_path = best_dir / out_name

    # backup se esiste
    if out_path.exists():
        bak = out_path.with_suffix(".csv.bak")
        shutil.copy2(out_path, bak)

    # --- write canonical, ordered, with blank separators ---
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["param", "value", "note"])
        for k in required_order:
            if k == "":
                w.writerow(["", "", ""])
                continue
            r = m[k]
            w.writerow([r["param"], r["value"], r["note"]])

    print(f"[AUTO_CAL][EXPORT] wizard config scritto: {out_path}")
    return out_path


import io
import pandas as pd

def _read_report_sections(report_path: str | Path) -> dict[str, pd.DataFrame]:
    """
    Legge un report CSV multi-sezione (formato: linee '### SHEET=NAME')
    e restituisce un dict: {section_name: DataFrame}.

    Robustezza:
    - prova prima sep=';' (EU-friendly) poi sep=','
    - usa engine='python' per tollerare righe irregolari
    - ignora righe vuote
    """
    text = Path(report_path).read_text(encoding="utf-8", errors="ignore").splitlines()

    sections: dict[str, list[str]] = {}
    current = None

    for line in text:
        s = line.strip()
        if not s:
            continue
        if s.startswith("###") and "SHEET=" in s:
            # es: ### SHEET=DATASET_SUMMARY
            current = s.split("SHEET=", 1)[1].strip()
            sections[current] = []
            continue
        if current is None:
            # prima sezione non dichiarata: la scartiamo
            continue
        sections[current].append(line)

    out: dict[str, pd.DataFrame] = {}

    for name, lines in sections.items():
        buf = "\n".join(lines).strip()
        if not buf:
            continue

        # Prova separatore ';' poi ','
        last_err = None
        for sep in (";", ","):
            try:
                df = pd.read_csv(
                    io.StringIO(buf),
                    sep=sep,
                    engine="python",
                )
                out[name] = df
                last_err = None
                break
            except Exception as e:
                last_err = e

        if last_err is not None:
            # fallback estremo: prova a saltare righe problematiche
            try:
                df = pd.read_csv(
                    io.StringIO(buf),
                    sep=";",
                    engine="python",
                    on_bad_lines="skip",
                )
                out[name] = df
            except Exception:
                # se proprio non si riesce, non bloccare tutto
                out[name] = pd.DataFrame()

    return out



def main() -> int:
    ap = argparse.ArgumentParser(
        prog="regime_auto_calibration",
        description="Regime Filter Automatic Calibration (stand-alone, wizard-safe).",
    )
    ap.add_argument("--input", required=True, help="Path CSV KPI input")
    ap.add_argument("--classifier", required=True, help="Module name, e.g. shared.regime_classifier_EQQQ_1d")
    ap.add_argument("--base-config", required=True, help="Path to base config CSV in shared/")
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--outdir", default="", help="Optional output dir (default: _data/regime_calibration_runs/<ts>/)")

    ap.add_argument(
        "--timeframe",
        default="1d",
        help="Timeframe del dataset (es: 30m, 1h, 1d, 1w). Default=1d",
    )
    args = ap.parse_args()

    # -----------------------------
    # Sanity check: classifier vs timeframe
    # -----------------------------
    def _normalize_tf(tf: str) -> str:
        t = (tf or "").strip().lower()
        # normalizza alias frequenti
        if t in ("30min", "30m", "m30"):
            return "30m"
        if t in ("1hour", "1h", "h1"):
            return "1h"
        if t in ("1day", "1d", "d1"):
            return "1d"
        if t in ("1week", "1w", "w1"):
            return "1w"
        return t

    tf = _normalize_tf(getattr(args, "timeframe", ""))
    clf = (args.classifier or "").lower()

    # euristiche: se nel nome classifier compare un timeframe, segnaliamo mismatch
    expected = None
    for token in ("30m", "1h", "1d", "1w"):
        if token in clf:
            expected = token
            break

    if expected and tf and expected != tf:
        print(
            f"[WARN] timeframe mismatch: --classifier='{args.classifier}' suggerisce '{expected}' "
            f"ma --timeframe='{args.timeframe}'. Verifica coerenza target/validazione."
        )

    base_cfg = Path(args.base_config)
    if not base_cfg.exists():
        root = Path(__file__).resolve().parents[2]  # Py_SUITE_TRADING
        fallback = root / "_data" / "config_filtro_regime" / base_cfg.name
        if fallback.exists():
            base_cfg = fallback
        else:
            raise FileNotFoundError(f"base-config non trovato: {base_cfg} (fallback provato: {fallback})")

    res = run_calibration(
        input_csv=Path(args.input),
        classifier_module=args.classifier,
        base_config_csv=base_cfg,  # ✅ usa fallback risolto
        trials=args.trials,
        seed=args.seed,
        outdir=Path(args.outdir) if args.outdir else None,
    )

    best_score = res.get("best_score", res.get("score"))
    best_config = (
            res.get("best_config")
            or res.get("best_config_csv")
            or res.get("best_config_path")
            or res.get("config_csv")
    )
    best_report = (
            res.get("best_report")
            or res.get("best_report_csv")
            or res.get("best_report_path")
            or res.get("report_csv")
    )
    trials_csv = (
            res.get("trials_csv")
            or res.get("trials_path")
            or res.get("trials")
    )

    print("\n===== REGIME AUTO CALIBRATION DONE =====")
    print(f"Best score: {best_score}")
    print(f"Best config: {best_config}")
    print(f"Best report: {best_report}")
    print(f"Trials CSV : {trials_csv}")

    # -------------------------------------------------------
    # EXPORT: genera config wizard-readable dentro /best
    # -------------------------------------------------------
    try:


        if best_config and best_report:
            best_dir = Path(best_report).parent  # .../best/
            # Infer symbol/timeframe dal best_config name (es: ..._EQQQ_1d_calibrated.csv)
            stem = Path(best_config).stem
            parts = stem.split("_")
            symbol = "UNKNOWN"
            tf = str(args.timeframe) if hasattr(args, "timeframe") else "1d"
            if parts[-1].lower() == "calibrated" and len(parts) >= 3:
                tf = parts[-2]
                symbol = parts[-3]

            _export_wizard_config_from_best_config(
                best_config_csv=Path(best_config),
                best_dir=best_dir,
                symbol=symbol,
                timeframe=tf,
            )
    except Exception as e:
        print(f"[AUTO_CAL][WARN] export wizard config fallito: {e}")


    # --- Stampa finale stile wizard (robusta: usa best/ se best_report manca) ---
    try:

        def _pick_best_report(run_dir: Path) -> Path | None:
            if not run_dir:
                return None
            best_dir = run_dir / "best"
            if not best_dir.exists():
                return None

            # 1) preferisci calibrated
            cand = sorted(best_dir.glob("*report*calibrated*.csv"))
            if cand:
                return cand[0]

            # 2) fallback: qualsiasi report csv
            cand = sorted(best_dir.glob("*report*.csv"))
            return cand[0] if cand else None

        report_printed = False

        # 1) prova best_report esplicito
        p_best = Path(best_report) if best_report else None
        if p_best and p_best.exists():
            _print_wizard_style_from_report(p_best)
            report_printed = True

            # Stampa bande observed vs target (da report, senza ri-applicare il regime)
            print_observed_vs_target_from_report(p_best, timeframe=args.timeframe)

        # --- VERDICT A/B/C colorato (stesso stile wizard) ---
        try:
            from shared.wizard_regime_filter import print_regime_validation_report
            from shared.regime_auto_calibration.parse_report import \
                load_report_csv  # se esiste già un loader nel tuo parse_report

            # Se non hai un loader, dimmelo: facciamo un mini-parser qui.
            stats_sheet, coverage_table = load_report_csv(p_best)  # <-- usa la tua funzione reale se già presente
            print("\n===== REGIME VALIDATION VERDICT (AUTO A/B/C) =====")

            import pandas as pd

            # stats_sheet: loader -> list[dict]  => il wizard vuole un DataFrame
            stats_df = pd.DataFrame(stats_sheet)

            # Se il report non contiene STATS, ricaviamo le metriche dal trials.csv (best row)
            if stats_df.empty or ("metric" not in stats_df.columns) or ("value" not in stats_df.columns):
                try:
                    trials_path = Path(trials_csv) if trials_csv else None
                    if trials_path and trials_path.exists():
                        t = pd.read_csv(trials_path)

                        # Se hai una colonna trial_id, prova a prendere il best trial da best_report "trial_XXXX"
                        best_trial_id = None
                        try:
                            if best_report:
                                m = re.search(r"trial_(\d+)", str(best_report))
                                if m:
                                    best_trial_id = f"trial_{m.group(1)}"
                        except Exception:
                            best_trial_id = None

                        row = None
                        if best_trial_id and "trial_id" in t.columns:
                            msk = (t["trial_id"].astype(str) == str(best_trial_id))
                            if msk.any():
                                row = t.loc[msk].iloc[0]

                        # fallback: prendi riga con score massimo
                        if row is None and "score" in t.columns:
                            row = t.sort_values("score", ascending=False).iloc[0]

                        if row is not None:
                            candidates = [
                                "chi2_pvalue",
                                "kruskal_r5_pvalue",
                                "max_abs_cliff_r5",
                                "spread_r5_mean",
                                "obj_J_cov",
                                "obj_J_chi2",
                                "obj_J_kr",
                            ]
                            rows = []
                            for k in candidates:
                                if k in t.columns:
                                    rows.append({"metric": k, "value": row[k]})
                            stats_df = pd.DataFrame(rows)

                except Exception as e:
                    print(f"[WARN] impossibile costruire stats_df da trials.csv: {e}")

            # Se ancora vuoto, non possiamo fare verdict PRO
            if stats_df.empty or ("metric" not in stats_df.columns) or ("value" not in stats_df.columns):
                raise ValueError("[AUTO_CAL] STATS non disponibili: né nel report né in trials.csv")

            print_regime_validation_report(
                stats_df,
                coverage_table=coverage_table,
                title="REGIME VALIDATION VERDICT",
            )
        except Exception as e:
            print(f"[WARN] verdict colorato non disponibile: {e}")


        else:
            # 2) ricava run_dir e cerca best/*report*.csv
            run_dir = None
            if trials_csv:
                run_dir = Path(trials_csv).parent
            elif args.outdir:
                run_dir = Path(args.outdir)

            p_best = _pick_best_report(run_dir) if run_dir else None
            if (not report_printed) and p_best and p_best.exists():
                _print_wizard_style_from_report(p_best)
                # In questo ramo non abbiamo già stampato la tabella observed
                print_observed_vs_target_from_report(p_best, timeframe=args.timeframe)
            else:
                # 3) ultima spiaggia: summary “light” senza report
                print(f"\n[INFO] Wizard-style summary per timeframe: {args.timeframe}")
                print_wizard_style_summary(
                    input_csv=Path(args.input),
                    best_config_csv=Path(best_config),
                    timeframe=args.timeframe,
                )

    except Exception as e:
        print(f"\n[WARN] stampa wizard-style fallita: {e}")
        if best_report:
            p = Path(best_report)
            if p.exists():
                print("\n[DBG] best_report (prime 40 righe):")
                try:
                    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for i, l in enumerate(lines[:40], start=1):
                        print(f"{i:03d} {l}")
                except Exception as e2:
                    print(f"[DBG] impossibile leggere best_report: {e2}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())