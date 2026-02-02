from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import pandas as pd

from .io import load_csv, export_csv
from .engine import run_qc


# ============================================================
# ARGPARSE
# ============================================================
def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="controllo_coerenza",
        description="Quality Control (QC) dei dati OHLCV"
    )

    p.add_argument(
        "--input",
        required=False,
        help="File CSV di input. Se omesso → selezione interattiva (solo RAW_*)."
    )

    # NOTE: reso opzionale per compatibilità pipeline
    p.add_argument(
        "--output-dir",
        required=False,
        help="Directory dati (input/output). Se omessa → PY_SUITE_DATA_DIR o fallback a Py_SUITE_TRADING/_data/Test Data."
    )

    p.add_argument(
        "--rules",
        nargs="*",
        default=None,
        help="Lista opzionale di regole QC da applicare (default: tutte)"
    )

    p.add_argument(
        "--prefix",
        default="CLEAN_",
        help="Prefisso file CLEAN di output (default: CLEAN_)"
    )

    p.add_argument(
        "--export-rejected",
        action="store_true",
        help="Esporta anche il file REJECTED_*.csv"
    )

    return p


# ============================================================
# DIR RESOLUTION (pipeline-friendly)
# ============================================================
def resolve_data_dir(output_dir_arg: str | None) -> Path:
    """
    Risoluzione directory dati:
    1) --output-dir (se fornita)
    2) env PY_SUITE_DATA_DIR (se presente)
    3) fallback: <Py_SUITE_TRADING>/_data/Test Data (assumendo module path dentro 1.1 Controllo_coerenza_dati)
    """
    if output_dir_arg:
        return Path(output_dir_arg).expanduser().resolve()

    env_dir = os.environ.get("PY_SUITE_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # fallback robusto: risali fino a Py_SUITE_TRADING (cartella padre della "1.1 Controllo_coerenza_dati")
    # __file__ = .../1.1 Controllo_coerenza_dati/controllo_coerenza/cli.py
    # parents[2] = .../1.1 Controllo_coerenza_dati
    # parents[3] = .../Py_SUITE_TRADING
    try:
        suite_root = Path(__file__).resolve().parents[3]
    except Exception:
        suite_root = Path.cwd().resolve()

    return (suite_root / "_data" / "Test Data").resolve()


# ============================================================
# INTERACTIVE FILE PICKER (solo RAW_*.csv)
# ============================================================
def pick_input_file(data_dir: Path) -> Path:
    csv_files = sorted(data_dir.glob("RAW_*.csv"), key=lambda p: p.name.lower())

    if not csv_files:
        print(f"❌ Nessun CSV RAW_* trovato in {data_dir}", file=sys.stderr)
        raise SystemExit(1)

    print("\nSeleziona file di input (solo RAW_*):\n")
    for i, p in enumerate(csv_files, start=1):
        print(f" {i:2d}) {p.name}")

    while True:
        choice = input("\nNumero file (INVIO per annullare): ").strip()
        if choice == "":
            print("⏹ Operazione annullata.")
            raise SystemExit(0)

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(csv_files):
                return csv_files[idx - 1]

        print("❌ Scelta non valida, riprova.")


# ============================================================
# MAIN
# ============================================================
def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    data_dir = resolve_data_dir(args.output_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # INPUT: diretto o interattivo
    # ------------------------------------------------------------
    if args.input:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.exists():
            print(f"❌ File non trovato: {input_path}", file=sys.stderr)
            return 1
    else:
        input_path = pick_input_file(data_dir)

    print(f"[INFO] QC input: {input_path}")
    print(f"[INFO] QC data dir: {data_dir}")

    # ------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------
    df = load_csv(input_path)

    if df.empty:
        print("⚠️ File vuoto: nessuna riga da processare")
        return 0

    print(f"[INFO] Righe caricate: {len(df)}")

    if "symbol" in df.columns and "isin" in df.columns:
        print(
            "[DEBUG] META (input):",
            "symbol=", df["symbol"].dropna().unique()[:3],
            "isin=", df["isin"].dropna().unique()[:3],
        )

    # ------------------------------------------------------------
    # RUN QC
    # ------------------------------------------------------------
    cleaned, rejected, stats = run_qc(df, selected_rules=args.rules)

    print(
        f"[INFO] QC stats: total={stats.total_rows} "
        f"kept={stats.kept_rows} "
        f"rejected={stats.rejected_rows} "
        f"({stats.rejected_pct:.2f}%)"
    )

    if stats.per_rule_rejections:
        print("[INFO] Rejections per rule:")
        for rule, cnt in stats.per_rule_rejections.items():
            print(f"  - {rule}: {cnt}")

    # ------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------
    clean_name = f"{args.prefix}{input_path.name}"
    clean_path = data_dir / clean_name

    export_csv(cleaned, clean_path)
    print(f"✅ CLEAN scritto: {clean_path}")

    if "symbol" in cleaned.columns and "isin" in cleaned.columns:
        print(
            "[DEBUG] META (clean):",
            "symbol=", cleaned["symbol"].dropna().unique()[:3],
            "isin=", cleaned["isin"].dropna().unique()[:3],
        )

    if args.export_rejected and not rejected.empty:
        rej_name = f"REJECTED_{input_path.name}"
        rej_path = data_dir / rej_name
        export_csv(rejected, rej_path)
        print(f"⚠️ REJECTED scritto: {rej_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

