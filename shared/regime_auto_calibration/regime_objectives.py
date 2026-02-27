from dataclasses import dataclass
from typing import Dict, Tuple, Callable, Any, List, Optional
import math



# ============================================================
# Result container
# ============================================================

@dataclass
class ObjectiveResult:
    score: float
    breakdown: Dict[str, float]
    hard_failed: bool
    reasons: List[str]


# ============================================================
# Helper utilities (riutilizzabili da tutte le objective)
# ============================================================

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _neglog10_p(p):
    if p is None or p <= 0:
        return 10.0
    return -math.log10(p)

def _coverage_to_pct(coverage: Dict[str, float]) -> Dict[str, float]:
    """
    Normalizza coverage a scala percentuale 0–100.
    Se i valori sembrano frazioni (max <= 1.5), moltiplica per 100.
    """
    if not coverage:
        return {}

    vals = []
    for v in coverage.values():
        try:
            vals.append(float(v))
        except Exception:
            pass

    if not vals:
        return {}

    mx = max(vals)
    if mx <= 1.5:
        return {k: (float(v) * 100.0 if v is not None else 0.0) for k, v in coverage.items()}

    return {k: (float(v) if v is not None else 0.0) for k, v in coverage.items()}



def _hard_constraints(
    coverage: Dict[str, float],
    n_by_regime: Dict[str, int],
    n_total: int,
    bands: Optional[Dict[str, Tuple[float, float]]] = None,
    unknown_max_pct: float = 1.0,
    min_n_frac: float = 0.03,
    min_n_floor: int = 3,
    enforce_min_n: bool = True,
):
    reasons = []
    hard_failed = False

    unknown_pct = coverage.get("UNKNOWN", 0.0)
    if unknown_pct > unknown_max_pct:
        hard_failed = True
        reasons.append(f"UNKNOWN pct {unknown_pct:.2f} > {unknown_max_pct}")

    if enforce_min_n:
        min_n = max(min_n_floor, int(math.ceil(min_n_frac * n_total)))

        for r, n in n_by_regime.items():
            if r == "UNKNOWN":
                continue

            # Applica min_n solo ai regimi che hanno una banda definita (non "n/a")
            if bands is not None:
                if r not in bands:
                    continue
                if bands.get(r) is None:
                    continue

                # Se la banda consente 0% (lower=0), il regime è opzionale:
                # non imporre min_n (può essere 0 o raro su campioni piccoli).
                lo, hi = bands[r]
                if float(lo) <= 0.0:
                    continue

            if enforce_min_n:
                if n < min_n:
                    hard_failed = True
                    reasons.append(f"{r} n={n} < {min_n}")

    return hard_failed, reasons




def _coverage_penalty(
    coverage: Dict[str, float],
    bands: Dict[str, Tuple[float, float]],
):
    penalties = []
    for r, (L, U) in bands.items():
        if r == "UNKNOWN":
            continue
        cov = coverage.get(r, 0.0)

        if L <= cov <= U:
            penalties.append(0.0)
        else:
            width = max(U - L, 1e-6)
            delta = max(0.0, L - cov, cov - U)
            penalties.append((delta / width) ** 2)

    if not penalties:
        return 0.0

    return sum(penalties) / len(penalties)


# ============================================================
# SIMPLE OBJECTIVE v0.9
# ============================================================

def objective_simple_v09(
    stats: Dict[str, Any],
    coverage: Dict[str, float],
    n_by_regime: Dict[str, int],
    bands: Dict[str, Tuple[float, float]],
    ctx: Dict[str, Any],
) -> ObjectiveResult:

    n_total = ctx.get("n_total", sum(n_by_regime.values()))
    coverage_pct = _coverage_to_pct(coverage)


    # ---------------- Hard constraints ----------------
    hard_failed, reasons = _hard_constraints(
        coverage_pct,
        n_by_regime,
        n_total,
        bands=bands,
        unknown_max_pct=float(ctx.get("hard_unknown_max_pct", 1.0)),
        min_n_frac=float(ctx.get("hard_min_n_frac", 0.03)),
        min_n_floor=int(ctx.get("hard_min_n_floor", 3)),
        enforce_min_n=bool(ctx.get("hard_enforce_min_n", False)),  # ✅ default False
    )

    if hard_failed:
        return ObjectiveResult(
            score=1e9,
            breakdown={},
            hard_failed=True,
            reasons=reasons,
        )

    # ---------------- Coverage penalty ----------------
    J_cov = _coverage_penalty(coverage_pct, bands)

    # ---------------- Chi2 penalty ----------------
    chi2_p = _safe_float(stats.get("chi2_pvalue"))
    J_chi2 = max(0.0, _neglog10_p(chi2_p) - 2.0)

    # ---------------- Kruskal penalty ----------------
    kr_p = _safe_float(stats.get("kruskal_r5_pvalue"))
    J_kr = max(0.0, _neglog10_p(kr_p) - 2.0)

    # ---------------- Final score ----------------
    score = 0.60 * J_cov + 0.25 * J_chi2 + 0.15 * J_kr

    return ObjectiveResult(
        score=score,
        breakdown={
            "J_cov": J_cov,
            "J_chi2": J_chi2,
            "J_kr": J_kr,
        },
        hard_failed=False,
        reasons=[],
    )


# ============================================================
# Registry
# ============================================================

OBJECTIVES: Dict[str, Callable[..., ObjectiveResult]] = {
    "simple_v09": objective_simple_v09,
}