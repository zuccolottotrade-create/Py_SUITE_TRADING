# Py_SUITE_TRADING/shared/regime_auto_calibration/score.py
from __future__ import annotations

import math
from typing import Dict, Any


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def score_from_metrics(m: Dict[str, float], *, debug: bool = False) -> float:
    """
    Score da massimizzare (timeframe-agnostic).

    ARCH v2:
      1) Coverage-first: massimizza l'aderenza alle bande target tramite `coverage_penalty`
         (calcolata a monte da report/parser, indipendente dal timeframe).
      2) Hard penalty se ci sono regimi fuori target: `cov_out_of_band_count`.
      3) Tie-break predittivo leggero (solo come secondario): spread forward returns / hit-rate,
         Cliff's delta, Kruskal (se presente).

    Metriche attese (se disponibili):
      - coverage_penalty (>=0): somma pesata delle distanze alla banda (delta-to-band)^2
      - cov_out_of_band_count (>=0): numero regimi fuori banda
      - spread_r5_mean, spread_r5_hit
      - max_abs_cliff_r5
      - kruskal_r5_pvalue (preferito) oppure kruskal_p_mean (fallback)
    """

    # ---------------------------
    # 1) Coverage (dominante)
    # ---------------------------
    missing_cov = "coverage_penalty" not in m
    cov_pen = _safe_float(m.get("coverage_penalty"), default=0.0)

    # Se manca completamente la coverage_penalty, trattiamolo come errore "hard":
    # senza coverage la calibrazione non ha l'obiettivo principale.
    if missing_cov:
        cov_pen = 1_000.0  # grande => S_cov ~ 0
        out_cnt = 5
    else:
        out_cnt = int(_safe_float(m.get("cov_out_of_band_count"), default=0.0))

    # Transform stabile in (0, 1]
    # (cov_pen=0 => 1; cov_pen grande => ~0)
    if cov_pen < 0:
        cov_pen = 0.0
    s_cov = 1.0 / (1.0 + cov_pen)

    # Hard penalty se fuori target (penalizza molto; coverage-first)
    hard_pen = 0.0
    if out_cnt > 0:
        # penalità fissa + piccola componente per regime fuori banda
        hard_pen = 12.0 * out_cnt

    # ---------------------------
    # 2) Predittivo (tie-break)
    # ---------------------------
    # Kruskal: preferisci pvalue r5; fallback su aggregato se disponibile
    kr_p = m.get("kruskal_r5_pvalue", None)
    if kr_p is None:
        kr_p = m.get("kruskal_p_mean", None)
    kr_p = _safe_float(kr_p, default=0.0)

    if kr_p > 0.0:
        kr_score = _clamp(-math.log10(kr_p), 0.0, 6.0)
    else:
        kr_score = 0.0

    spread = _safe_float(m.get("spread_r5_mean"), default=0.0)
    spread_hit = _safe_float(m.get("spread_r5_hit"), default=0.0)
    cliff = abs(_safe_float(m.get("max_abs_cliff_r5"), default=0.0))

    # Clamp per robustezza (evita che un singolo outlier domini)
    spread_c = _clamp(spread, 0.0, 0.03)         # 0-3% su R5 tipico
    spread_hit_c = _clamp(spread_hit, 0.0, 0.30) # 0-30% differenza hit-rate
    cliff_c = _clamp(cliff, 0.0, 0.50)

    # Se coverage è fuori target, riduci peso predittivo (non deve "bypassare" i vincoli)
    pred_mult = 1.0 if out_cnt == 0 else 0.2

    s_pred = 0.0
    s_pred += 0.5 * kr_score
    s_pred += 1.0 * spread_c
    s_pred += 1.0 * spread_hit_c
    s_pred += 0.5 * cliff_c
    s_pred *= pred_mult

    # ---------------------------
    # 3) Score finale
    # ---------------------------
    # Coverage domina: scala 0..100 circa. Pred è tie-break: scala ~0..(pochi punti).
    score = 0.0
    score += 100.0 * s_cov
    score += 10.0 * s_pred
    score -= hard_pen


    if debug:
        print("\n===== SCORE DEBUG BREAKDOWN =====")
        print(f"coverage_penalty={cov_pen:.6f}  -> s_cov={s_cov:.6f}  (100*s_cov={100.0*s_cov:.3f})")
        print(f"cov_out_of_band_count={out_cnt} -> hard_pen={hard_pen:.3f}")
        print(f"kruskal_p={kr_p:.6g} -> kr_score={kr_score:.3f}")
        print(f"spread_r5_mean={spread:.6g} (clamped={spread_c:.6g})")
        print(f"spread_r5_hit ={spread_hit:.6g} (clamped={spread_hit_c:.6g})")
        print(f"max_abs_cliff_r5={cliff:.6g} (clamped={cliff_c:.6g})")
        print(f"pred_mult={pred_mult:.3f}  s_pred={s_pred:.6f}  (10*s_pred={10.0*s_pred:.3f})")
        print(f"FINAL SCORE={score:.6f}")
        print("=================================\n")

    return float(score)