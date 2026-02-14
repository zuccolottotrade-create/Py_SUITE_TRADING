#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

# --- bootstrap: garantisce import da Py_SUITE_TRADING root ---
SUITE_ROOT = Path(__file__).resolve().parents[1]  # cartella che contiene "shared"
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))


# ----------------------------
# Helpers UI
# ----------------------------
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
    from loader_regime import list_regime_modules

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
    from loader_regime import load_regime_apply
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

# ============================================================
# REGIME_L1 – Target di riferimento (timeframe 30m)
# Include tutti i regimi canonici + fallback UNKNOWN
# ============================================================
REGIME_L1_TARGETS_30M = {
    "TREND":    (25.0, 45.0),
    "RANGE":    (30.0, 55.0),
    "LATERAL":  (30.0, 55.0),
    "VOLATILE": (5.0,  20.0),
    "UNKNOWN":  (0.0,  0.0),
}

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
    targets: dict[str, tuple[float, float]] = REGIME_L1_TARGETS_30M,
    timeframe_label: str = "30m",
) -> None:
    regimes = list(targets.keys())
    extras = sorted([r for r in regime_coverage_pct.keys() if r not in targets])
    regimes += extras

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

    out_of_target = []

    for r in regimes:
        obs = float(regime_coverage_pct.get(r, 0.0) or 0.0)

        if r in targets:
            lo, hi = targets[r]
            if obs < lo:
                delta = obs - lo
                status = "OUT"
                out_of_target.append(r)
            elif obs > hi:
                delta = obs - hi
                status = "OUT"
                out_of_target.append(r)
            else:
                delta = 0.0
                status = "IN"
            target_str = f"{lo:.0f}–{hi:.0f}"
        else:
            delta = 0.0
            status = "N/A"
            target_str = "n/a"

        print(f"{r:<12} | {obs:>10.2f} | {target_str:>13} | {delta:>13.2f} | {status:<6}")

    if out_of_target:
        print("\n[REGIME][STATUS] ⚠ CALIBRAZIONE NECESSARIA")
        print("[REGIME][DETAIL] Regimi fuori target:", ", ".join(out_of_target))
    else:
        print("\n[REGIME][STATUS] ✓ Coverage entro i range target")


# ----------------------------
# MAIN
# ----------------------------
def main() -> int:
    # suite_root = cartella che contiene "shared"
    suite_root = Path(__file__).resolve().parents[1]
    shared_dir = suite_root / "shared"
    default_in_repo = suite_root / "_data" / "Test Data"
    default_out_repo = suite_root / "_data" / "config_filtro_regime"


    print("======================================")
    print(" Regime Filter Wizard (apply + report)")
    print("======================================")

    # STEP 1: scegli filtro regime_* da /shared
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

    # Applica filtro
    print(f"[INFO] Applico filtro regime: {regime_module}")
    df2 = apply_fn(df)

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
    # DEBUG RAW: stampa stringhe così come sono nel CSV (no conversion)
    # ------------------------------------------------------------
    for c in ["KPI_ADX_14", "KPI_ATR_PCT_14", "KPI_EMA_21"]:
        if c in df.columns:
            print(f"[DBG][RAW] {c} head:", df[c].astype(str).head(5).tolist())

    # ------------------------------------------------------------
    # DEBUG KPI reali (NaN% + min/max) per capire UNKNOWN=100%
    # ------------------------------------------------------------
    kpi_check = ["KPI_ADX_14", "KPI_ATR_PCT_14", "KPI_EMA_21", "KPI_EMA_50", "KPI_EMA_200"]
    for c in kpi_check:
        if c in df2.columns:
            s = df2[c]
            # prova conversione EU->float per diagnostica
            s_num = pd.to_numeric(s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                                  errors="coerce")
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

        # BB width: varianti possibili
        "KPI_BB_WIDTH_20",
        "KPI_BB_WIDTH_PCT",
        "KPI_BB_WIDTH",
        "BB_WIDTH",
    ]

    present = [c for c in candidates if c in df2.columns]
    missing = [c for c in candidates if c not in df2.columns]

    print(f"[DBG][REGIME] KPI candidates present: {present}")
    print(f"[DBG][REGIME] KPI candidates missing: {missing}")

    for c in present:
        na_rate = float(df2[c].isna().mean() * 100.0)
        print(f"[DBG][REGIME] {c} NaN% = {na_rate:.2f}")

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

    print_regime_coverage_table_vs_target(
        coverage_pct,
        targets=REGIME_L1_TARGETS_30M,
        timeframe_label="30m",
    )

    out_name = f"REGIME_REPORT_{in_file.stem}.csv"
    out_path = out_repo / out_name




    write_single_csv_report(out_path, sheets)

    print(f"[OK] Report scritto: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
