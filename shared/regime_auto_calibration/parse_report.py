# Py_SUITE_TRADING/shared/regime_auto_calibration/parse_report.py
from __future__ import annotations

from pathlib import Path
from typing import Dict
import csv

def _safe_float(x: str):
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    # support EU comma
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _read_sheet_from_report(path: Path, sheet_name: str):
    """
    Legge una singola sezione "### SHEET=<sheet_name>" dal CSV multi-sezione.
    Ritorna list[dict] (DictReader) con autodetect delimiter (EU ';' vs US ',').
    """
    sheet = (sheet_name or "").strip().upper()
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("### SHEET=") and line.replace("### SHEET=", "").strip().upper() == sheet:
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            block = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("### SHEET="):
                block.append(lines[i])
                i += 1
            if not block:
                return []
            hdr = block[0]
            delim = ";" if hdr.count(";") > hdr.count(",") else ","
            reader = csv.DictReader(block, delimiter=delim)
            return list(reader)
        i += 1
    return []


def parse_regime_report_csv(path: Path) -> Dict[str, float]:
    """
    Legge il report CSV standard (sezioni ### SHEET=...) ed estrae metriche (metric->float).
    Deve supportare sia vecchi report con SHEET=STATS sia nuovo standard:
      - SHEET=REGIME_SEPARATION_TESTS
      - SHEET=FORWARD_RETURNS_BY_REGIME
    """
    metrics: Dict[str, float] = {}

    # Riusa il loader “canonico” (evita doppie logiche divergenti)
    stats_sheet, _coverage_table = load_report_csv(path)

    for r in stats_sheet:
        m = (r.get("metric") or "").strip()
        v = _safe_float(r.get("value"))
        if m and v is not None:
            metrics[m] = float(v)

    return metrics

# ============================================================
# Extended extractor for auto-calibration objective
# ============================================================

def extract_inputs_for_objective(path: Path):
    """
    Estrae gli input minimi per le objective-functions (regime_objectives):
      - stats (metric -> value)  [da DATASET_SUMMARY + REGIME_SEPARATION_TESTS + FORWARD_RETURNS_BY_REGIME]
      - coverage (regime -> observed %)
      - n_by_regime (regime -> N bars)
      - n_total

    Nota: il report è un singolo CSV con sezioni "### SHEET=...".
    Riusa sempre `load_report_csv()` per evitare logiche divergenti (delimiter, formati legacy, ecc.).
    """
    # stats_sheet: list[{"metric","value"}]
    stats_sheet, _coverage_table = load_report_csv(path)

    stats: Dict[str, float] = {}
    for r in stats_sheet:
        m = (r.get("metric") or "").strip()
        v = _safe_float(r.get("value"))
        if m and v is not None:
            stats[m] = float(v)

    # Leggi direttamente REGIME_COVERAGE: righe "bars" e "pct"
    cov_rows = _read_sheet_from_report(Path(path), "REGIME_COVERAGE")
    coverage: Dict[str, float] = {}
    n_by_regime: Dict[str, int] = {}

    if cov_rows:
        first_row = cov_rows[0]
        metric_col = None
        for k in first_row.keys():
            if k and k.strip().upper() in ("REGIME_L1", "METRIC", "ROW", "NAME"):
                metric_col = k
                break
        if metric_col is None:
            metric_col = list(first_row.keys())[0]

        bars_row = None
        pct_row = None
        for r in cov_rows:
            name = (r.get(metric_col) or "").strip().lower()
            if name in ("bars", "n", "count"):
                bars_row = r
            elif name in ("pct", "percent", "percentage", "share"):
                pct_row = r

        if bars_row:
            for k, v in bars_row.items():
                if k == metric_col:
                    continue
                reg = (k or "").strip().upper()
                n = _safe_float(v)
                if reg and n is not None:
                    n_by_regime[reg] = int(round(n))

        if pct_row:
            for k, v in pct_row.items():
                if k == metric_col:
                    continue
                reg = (k or "").strip().upper()
                obs = _safe_float(v)
                if reg and obs is not None:
                    coverage[reg] = float(obs)

    # Se il report esprime coverage in frazione (0..1), convertilo a percentuale
    if coverage:
        mx = max(coverage.values())
        if mx <= 1.5:
            coverage = {k: float(v) * 100.0 for k, v in coverage.items()}

    # n_total: preferisci rows_used da DATASET_SUMMARY se presente
    n_total = int(round(stats.get("rows_used", 0.0))) if "rows_used" in stats else int(sum(n_by_regime.values()))

    return stats, coverage, n_by_regime, n_total
# ============================================================
# Loader per CLI (stats_sheet + coverage_table) usato dal verdict colorato
# ============================================================

def load_report_csv(path: str | Path):
    """
    Carica il report CSV multi-sezione (### SHEET=...) e ritorna:
      - stats_sheet: list[dict] con chiavi {metric, value}
      - coverage_table: list[tuple] (regime, observed, target_str, delta_to_band, status)

    Ora supporta anche:
      - SHEET=REGIME_SEPARATION_TESTS  -> metriche globali (kruskal/chi2 ecc)
      - SHEET=FORWARD_RETURNS_BY_REGIME -> metriche per-regime (r1/r5/hit/cliff)
    """
    import csv
    import math
    from pathlib import Path


    p = Path(path)
    stats_sheet = []

    with p.open("r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    def _read_sheet(sheet_name: str):
        sheet = sheet_name.upper()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("### SHEET=") and line.replace("### SHEET=", "").strip().upper() == sheet:
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                block = []
                while i < len(lines) and lines[i].strip() and not lines[i].startswith("### SHEET="):
                    block.append(lines[i])
                    i += 1
                if not block:
                    return []
                # autodetect delimiter (EU: ';' / US: ',') + fallback robusto
                hdr = block[0]
                delim_guess = ";" if hdr.count(";") > hdr.count(",") else ","

                def _parse_with(delim: str):
                    rr = csv.DictReader(block, delimiter=delim)
                    rows = list(rr)
                    fns = rr.fieldnames or []
                    fns_norm = [str(x).strip() for x in fns if x is not None]

                    # Se l'header collassa in una sola colonna che contiene separatori,
                    # il delimiter scelto è errato.
                    if len(fns_norm) == 1:
                        h0 = fns_norm[0]
                        if (";" in h0 and delim != ";") or ("," in h0 and delim != ","):
                            return None
                    return rows

                rows = _parse_with(delim_guess)
                if rows is None:
                    rows = _parse_with(";" if delim_guess == "," else ",")
                if rows is None:
                    rows = []

                return rows
            i += 1
        return []

    def _safe_float(x):
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if not s:
            return None
        # supporta virgola decimale
        s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None
    # ------------------------------------------------------------
    # Target bands resolver (timeframe-agnostic)
    # ------------------------------------------------------------
    def _resolve_targets(timeframe_label: str | None):
        """
        Ritorna (targets_dict, tf_label).
        targets_dict: regime -> (lo, hi) oppure None per n/a
        Nota: TREND è aggregato (TREND_UP + TREND_DOWN) ai fini del vincolo.
        """
        tf = (timeframe_label or "").strip().lower()

        # 1) prova a riusare targets dal wizard (se esposti)
        try:
            import importlib
            wz = importlib.import_module("shared.wizard_regime_filter")
            # pattern comuni: dict per timeframe oppure funzione
            if hasattr(wz, "REGIME_TARGETS_BY_TIMEFRAME"):
                d = getattr(wz, "REGIME_TARGETS_BY_TIMEFRAME")
                if isinstance(d, dict):
                    if tf in d:
                        return d[tf], tf
                    if "default" in d:
                        return d["default"], "default"
            if hasattr(wz, "_get_targets_for_timeframe"):
                # funzione già presente nel tuo ecosistema wizard-style
                targets, tf_label = wz._get_targets_for_timeframe(tf if tf else "default")  # type: ignore
                return targets, tf_label
        except Exception:
            pass

        # 2) fallback default (timeframe-agnostic: "DEFAULT")
        DEFAULT = {
            "TREND": (25.0, 45.0),
            "RANGE": (30.0, 55.0),
            "LATERAL": (30.0, 55.0),
            "VOLATILE": (5.0, 20.0),
            "UNKNOWN": (0.0, 0.0),
            # TREND_UP / TREND_DOWN non vincolati singolarmente qui (n/a)
        }
        return DEFAULT, "default"

    def _band_distance(obs: float, band):
        if band is None:
            return 0.0, "N/A"
        lo, hi = band
        if obs < lo:
            return float(lo - obs), "OUT"
        if obs > hi:
            return float(obs - hi), "OUT"
        return 0.0, "IN"

    # ------------------------------------------------------------
    # 0) DATASET_SUMMARY -> metriche globali utili (es. timeframe_label)
    # ------------------------------------------------------------
    ds_rows = _read_sheet("DATASET_SUMMARY")
    timeframe_label = None
    for r in ds_rows:
        m0 = (r.get("metric") or "").strip()
        v0 = r.get("value")
        if m0:
            stats_sheet.append({"metric": m0, "value": v0})
        if m0.strip().lower() in ("timeframe", "timeframe_label", "tf", "tf_label"):
            timeframe_label = str(v0).strip().lower() if v0 is not None else None

    # ------------------------------------------------------------
    # 1) STATS base: prova STATS (se presente) altrimenti vuoto
    # ------------------------------------------------------------
    stats_sheet = []
    stats_rows = _read_sheet("STATS")
    for r in stats_rows:
        m = (r.get("metric") or "").strip()
        v = r.get("value")
        if m:
            stats_sheet.append({"metric": m, "value": v})

    # ------------------------------------------------------------
    # 2) Coverage: da REGIME_COVERAGE (righe bars/share)
    # ------------------------------------------------------------
    cov_rows = _read_sheet("REGIME_COVERAGE")
    coverage = {}

    if cov_rows:
        # identifica colonna “metrica” (REGIME_L1 oppure prima colonna)
        first_row = cov_rows[0]
        metric_col = None
        for k in first_row.keys():
            if k and k.strip().upper() in ("REGIME_L1", "METRIC", "ROW", "NAME"):
                metric_col = k
                break
        if metric_col is None:
            metric_col = list(first_row.keys())[0]

        share_row = None
        for r in cov_rows:
            name = (r.get(metric_col) or "").strip().lower()
            if name in ("share", "pct", "percent", "percentage"):
                share_row = r
                break

        if share_row:
            for k, v in share_row.items():
                if k == metric_col:
                    continue
                regime = (k or "").strip()
                obs = _safe_float(v)
                if regime and obs is not None:
                    coverage[regime] = float(obs)

    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # 2bis) Coverage metrics + penalty (coverage-first objective)
    # ------------------------------------------------------------
    # Normalizza chiavi a UPPER (per coerenza)
    cov_u = {}
    for k, v in coverage.items():
        kk = (k or "").strip().upper()
        vv = _safe_float(v)
        if kk and vv is not None:
            cov_u[kk] = float(vv)

    # Se il report esprime coverage in frazione (0..1), convertilo a percentuale
    if cov_u:
        mx = max(cov_u.values())
        if mx <= 1.5:
            cov_u = {k: float(v) * 100.0 for k, v in cov_u.items()}

    # TREND aggregato = TREND_UP + TREND_DOWN (se TREND non presente)
    if "TREND" not in cov_u:
        cov_u["TREND"] = float(cov_u.get("TREND_UP", 0.0) + cov_u.get("TREND_DOWN", 0.0))

    # Targets (timeframe-agnostic)
    targets, tf_label = _resolve_targets(timeframe_label)

    # Coverage penalty NORMALIZZATA (coerente con regime_objectives._coverage_penalty):
    # media su regimi vincolati di ((delta / band_width)^2). Valori tipici: 0..~20
    penalties = []
    out_cnt = 0

    if isinstance(targets, dict):
        for reg, band in targets.items():
            if reg == "UNKNOWN":
                continue
            if band is None:
                continue
            lo, hi = band
            width = max(float(hi) - float(lo), 1e-6)
            obs = float(cov_u.get(reg, 0.0))
            if lo <= obs <= hi:
                delta = 0.0
            else:
                delta = max(0.0, float(lo) - obs, obs - float(hi))
                out_cnt += 1
            penalties.append((delta / width) ** 2)

    cov_pen = (sum(penalties) / len(penalties)) if penalties else 0.0

    # Tabella coverage (per CLI verdict): include anche regimi N/A
    coverage_table = []
    for reg in ["TREND", "RANGE", "LATERAL", "VOLATILE", "UNKNOWN", "TREND_DOWN", "TREND_UP"]:
        obs = float(cov_u.get(reg, 0.0))
        band = targets.get(reg) if isinstance(targets, dict) else None

        delta, status = _band_distance(obs, band)
        targ_str = "n/a" if band is None else f"{band[0]}–{band[1]}"
        coverage_table.append((reg, obs, targ_str, float(delta), status))

        # Metriche per debug
        stats_sheet.append({"metric": f"cov_obs_pct_{reg}", "value": obs})
        stats_sheet.append({"metric": f"cov_dist_{reg}", "value": float(delta)})

    # Metriche per scoring/debug (legacy-friendly)
    stats_sheet.append({"metric": "coverage_penalty", "value": float(cov_pen)})
    stats_sheet.append({"metric": "cov_out_of_band_count", "value": float(out_cnt)})
    stats_sheet.append({"metric": "timeframe_label", "value": tf_label})
    # ------------------------------------------------------------
    # 3bis) REGIME_SEPARATION_TESTS
    # supporta:
    #  A) formato standard: metric;value
    #  B) formato verticale: una colonna con key e riga successiva con value
    # ------------------------------------------------------------
    sep_rows = _read_sheet("REGIME_SEPARATION_TESTS")

    if sep_rows:
        # --------------------------------------------------
        # CASO A: formato standard con colonne metric/value
        # --------------------------------------------------
        if ("metric" in sep_rows[0]) and ("value" in sep_rows[0]):
            for r in sep_rows:
                m = (r.get("metric") or "").strip()
                v = _safe_float(r.get("value"))
                if m and v is not None:
                    stats_sheet.append({"metric": m, "value": v})

            # --- Normalizzazione chiavi attese dall'objective ---
            for r in sep_rows:
                # Varianti come colonne
                v = _safe_float(r.get("chi2_pvalue_coverage"))
                if v is not None:
                    stats_sheet.append({"metric": "chi2_pvalue", "value": v})

                v = _safe_float(r.get("kruskal_pvalue_r5"))
                if v is not None:
                    stats_sheet.append({"metric": "kruskal_r5_pvalue", "value": v})

                # Varianti come metric/value
                m = (r.get("metric") or "").strip().lower()
                if m in ("chi2_pvalue_coverage", "chi2_coverage_pvalue", "chi2_p"):
                    v = _safe_float(r.get("value"))
                    if v is not None:
                        stats_sheet.append({"metric": "chi2_pvalue", "value": v})

                if m in ("kruskal_pvalue_r5", "kruskal_r5_p", "kruskal_p_r5"):
                    v = _safe_float(r.get("value"))
                    if v is not None:
                        stats_sheet.append({"metric": "kruskal_r5_pvalue", "value": v})

        # --------------------------------------------------
        # CASO B: formati non standard
        # --------------------------------------------------
        else:

            # -------------------------------
            # B1: singola colonna tipo:
            # kruskal_p_mean
            # 0.36
            # -------------------------------
            direct_added = False

            for r in sep_rows:
                if isinstance(r, dict) and len(r) == 1:
                    k = next(iter(r.keys()))
                    v_raw = r.get(k)

                    k_s = (k or "").strip()
                    v = _safe_float(v_raw)

                    if k_s and v is not None:
                        stats_sheet.append({"metric": k_s, "value": v})
                        direct_added = True

                        # 🔁 Normalizzazione diretta per objective
                        k_low = k_s.lower()
                        if k_low in ("kruskal_p_mean", "kruskal_p"):
                            stats_sheet.append(
                                {"metric": "kruskal_r5_pvalue", "value": v}
                            )
                        if k_low in ("chi2_p_mean", "chi2_p"):
                            stats_sheet.append(
                                {"metric": "chi2_pvalue", "value": v}
                            )

            # -------------------------------
            # B2: formato verticale alternato
            # key, value, key, value
            # -------------------------------
            if not direct_added:
                tokens = []

                for r in sep_rows:
                    # prima prova con values
                    for vv in r.values():
                        s = (vv or "").strip()
                        if s:
                            tokens.append(s)
                            break
                    else:
                        # fallback su keys
                        for kk in r.keys():
                            s = (kk or "").strip()
                            if s:
                                tokens.append(s)
                                break

                for i in range(0, len(tokens) - 1, 2):
                    key = tokens[i].strip()
                    val = _safe_float(tokens[i + 1])

                    if key and val is not None:
                        stats_sheet.append({"metric": key, "value": val})

                        # 🔁 Normalizzazione
                        key_low = key.lower()
                        if key_low in ("kruskal_p_mean", "kruskal_p"):
                            stats_sheet.append(
                                {"metric": "kruskal_r5_pvalue", "value": val}
                            )
                        if key_low in ("chi2_p_mean", "chi2_p"):
                            stats_sheet.append(
                                {"metric": "chi2_pvalue", "value": val}
                            )

    # ------------------------------------------------------------
    # 4) FORWARD_RETURNS_BY_REGIME -> supporta:
    #    A) formato "wide" legacy: r5_mean, r5_hit, cliff5...
    #    B) formato "long" nuovo: mean;median;...;hit_rate;regime;H
    # ------------------------------------------------------------
    fr_rows = _read_sheet("FORWARD_RETURNS_BY_REGIME")

    # raccogliamo mean per H=5 per calcolare spread_r5_mean
    r5_means = []
    cliffs = []

    if fr_rows:
        keys0 = [k.strip() if k else "" for k in fr_rows[0].keys()]
        keys0_u = [k.upper() for k in keys0]

        is_long = ("H" in keys0_u) and ("MEAN" in keys0_u) and ("REGIME" in keys0_u or "REGIME_L1" in keys0_u)
        is_wide = any(k.upper() in ("R5_MEAN", "R1_MEAN", "CLIFF5", "CLIFF_R5") for k in keys0_u)

        def _get_key(*cands: str):
            for c in cands:
                for k in fr_rows[0].keys():
                    if (k or "").strip().upper() == c.strip().upper():
                        return k
            return None

        if is_long:
            k_reg = _get_key("REGIME", "REGIME_L1")
            k_h = _get_key("H", "HORIZON")
            k_mean = _get_key("MEAN")
            k_hit = _get_key("HIT_RATE", "HIT", "HITRATE")

            for r in fr_rows:
                reg = (r.get(k_reg) or "").strip().upper() if k_reg else ""
                h = _safe_float(r.get(k_h)) if k_h else None
                mu = _safe_float(r.get(k_mean)) if k_mean else None
                hit = _safe_float(r.get(k_hit)) if k_hit else None

                if not reg or h is None:
                    continue

                # esponi metriche per debug: r{H}_mean_<REG>, r{H}_hit_<REG>
                if mu is not None:
                    stats_sheet.append({"metric": f"r{int(h)}_mean_{reg}", "value": mu})
                if hit is not None:
                    stats_sheet.append({"metric": f"r{int(h)}_hit_{reg}", "value": hit})

                # per spread score: H=5
                if int(h) == 5 and mu is not None:
                    r5_means.append(mu)

            # NB: nel formato long non abbiamo cliff -> resta 0 (ok)

        elif is_wide:
            # legacy / wide (compat)
            # tenta di capire nome colonna regime
            regime_key = _get_key("REGIME", "REGIME_L1")
            if regime_key is None:
                regime_key = list(fr_rows[0].keys())[0]

            col_map = {
                "r1_mean": ("r1_mean", ("r1_mean", "r1_avg")),
                "r1_hit": ("r1_hit", ("r1_hit", "r1_hit_rate")),
                "r5_mean": ("r5_mean", ("r5_mean", "r5_avg")),
                "r5_hit": ("r5_hit", ("r5_hit", "r5_hit_rate")),
                "cliff5": ("cliff5", ("cliff5", "cliff_r5", "cliff5_vs_best")),
            }

            for r in fr_rows:
                reg = (r.get(regime_key) or "").strip().upper()
                if not reg:
                    continue

                for out_name, (_, candidates) in col_map.items():
                    val = None
                    for ck in candidates:
                        if ck in r:
                            val = _safe_float(r.get(ck))
                            break
                    if val is None:
                        continue
                    stats_sheet.append({"metric": f"{out_name}_{reg}", "value": val})

                v_r5 = _safe_float(r.get("r5_mean"))
                if v_r5 is not None:
                    r5_means.append(v_r5)

                v_cl = _safe_float(r.get("cliff5")) or _safe_float(r.get("cliff_r5"))
                if v_cl is not None:
                    cliffs.append(v_cl)

    # metriche globali richieste dallo score/verdict
    if r5_means:
        spread = max(r5_means) - min(r5_means)
        stats_sheet.append({"metric": "spread_r5_mean", "value": spread})

    if cliffs:
        max_abs = max(abs(x) for x in cliffs if x is not None and not math.isnan(x))
        stats_sheet.append({"metric": "max_abs_cliff_r5", "value": max_abs})

    return stats_sheet, coverage_table