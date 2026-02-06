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

    # STEP 6: genera report
    build_regime_report, write_single_csv_report = _import_report_tools(suite_root)

    print("[INFO] Genero report filtro (CSV singolo)...")
    sheets = build_regime_report(df2, regime_col="REGIME_L1")


    out_name = f"REGIME_REPORT_{in_file.stem}.csv"
    out_path = out_repo / out_name
    write_single_csv_report(out_path, sheets)

    print(f"[OK] Report scritto: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
