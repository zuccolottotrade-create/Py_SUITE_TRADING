from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Optional

from .engine import run_qc
from .io import export_csv, load_csv

# Default: ../_data/Test Data
DEFAULT_TEST_DATA_DIR = (Path(__file__).resolve().parents[1] / "../_data/Test Data").resolve()


def _pipe_mode() -> bool:
    return os.environ.get("PIPELINE_MODE", "0").strip() == "1"


def ask_path(prompt: str, default: Path) -> Path:
    while True:
        s = input(f"{prompt}\n[{default}]: ").strip()
        if not s:
            return default.resolve()
        p = Path(s).expanduser()
        if p.exists():
            return p.resolve()
        print("Path non valido.")


def list_csv_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []

    EXCLUDE_PREFIXES = ("REPORT_", "SIGNAL_", "KPI_", "CLEAN_", "REJECT_", "QC_")

    files: List[Path] = []
    for p in folder.glob("*.csv"):
        if p.name.startswith(EXCLUDE_PREFIXES):
            continue
        files.append(p)

    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def ask_select_file(files: List[Path]) -> Path:
    if not files:
        raise FileNotFoundError("Nessun CSV trovato nella directory indicata.")
    print("\nSu quale file vuoi eseguire il controllo coerenza? (*.csv)")
    for i, f in enumerate(files, start=1):
        print(f"  {i}. {f.name}")
    while True:
        s = input("Seleziona un numero: ").strip()
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(files):
                return files[idx - 1]
        print("Selezione non valida.")


def _resolve_out_dir_from_output_arg(output_arg: str | None, fallback_dir: Path) -> Path:
    """
    Interpreta --output-csv come:
    - directory (se punta a una cartella esistente o termina con "/")
    - altrimenti prende la parent directory del file indicato
    Se non passato, usa fallback_dir.

    NOTA: Il nome dell'output CLEAN è SEMPRE: CLEAN_<nome_input>
    """
    if not output_arg:
        return fallback_dir.resolve()

    s = output_arg.strip()
    p = Path(s).expanduser()

    # caso: termina con "/" => directory
    if s.endswith("/") or s.endswith(os.sep):
        return p.resolve()

    # caso: path esistente ed è directory
    if p.exists() and p.is_dir():
        return p.resolve()

    # caso: è un file path -> usa la sua directory
    return p.parent.resolve()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Controllo_coerenza_dati - QC & cleaning CSV estrazione_pro"
    )
    p.add_argument("--input-csv", default=None)
    p.add_argument(
        "--output-csv",
        default=None,
        help=(
            "Per questo modulo, il nome dell'output CLEAN è sempre CLEAN_<input>. "
            "Questo argomento serve solo a indicare la cartella di output "
            "(o un path file da cui ricavare la cartella)."
        ),
    )
    p.add_argument("--rejected-csv", default="")
    p.add_argument("--report-csv", default="")
    p.add_argument("--sep", default=";")
    p.add_argument("--rules", default="", help="Comma-separated rule names (empty = all).")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    selected_rules = [r.strip() for r in args.rules.split(",") if r.strip()] or None

    input_csv: Path
    out_dir: Path
    base: str
    output_csv: Path
    rejected_csv: Path
    report_csv: Path

    # ==========================================================
    # Modalità pipeline (no interazione)
    # ==========================================================
    if _pipe_mode():
        if not args.input_csv or not args.output_csv:
            raise SystemExit("PIPELINE_MODE=1: devi passare --input-csv e --output-csv")

        input_csv = Path(args.input_csv).expanduser().resolve()

        # --output-csv decide SOLO la cartella; nome fisso CLEAN_<input>
        out_dir = _resolve_out_dir_from_output_arg(args.output_csv, input_csv.parent)
        out_dir.mkdir(parents=True, exist_ok=True)

        base = input_csv.name
        output_csv = out_dir / f"CLEAN_{base}"

        # Default automatici: crea SEMPRE REJECT_ e QC_ se non passati
        rejected_csv = (
            Path(args.rejected_csv).expanduser().resolve()
            if args.rejected_csv
            else (out_dir / f"REJECT_{base}")
        )
        report_csv = (
            Path(args.report_csv).expanduser().resolve()
            if args.report_csv
            else (out_dir / f"QC_{base}")
        )

    # ==========================================================
    # Modalità stand-alone
    # ==========================================================
    else:
        # -------------------------
        # Non interattiva: input+output passati
        # -------------------------
        if args.input_csv and args.output_csv:
            input_csv = Path(args.input_csv).expanduser().resolve()

            out_dir = _resolve_out_dir_from_output_arg(args.output_csv, input_csv.parent)
            out_dir.mkdir(parents=True, exist_ok=True)

            base = input_csv.name
            output_csv = out_dir / f"CLEAN_{base}"

            # Default automatici: crea SEMPRE REJECT_ e QC_ se non passati
            rejected_csv = (
                Path(args.rejected_csv).expanduser().resolve()
                if args.rejected_csv
                else (out_dir / f"REJECT_{base}")
            )
            report_csv = (
                Path(args.report_csv).expanduser().resolve()
                if args.report_csv
                else (out_dir / f"QC_{base}")
            )

        # -------------------------
        # Interattiva
        # -------------------------
        else:
            search_dir = ask_path(
                "Inserisci il path dove ricercare il file CSV di input",
                DEFAULT_TEST_DATA_DIR,
            )
            files = list_csv_files(search_dir)
            input_csv = ask_select_file(files)

            out_dir = ask_path(
                "Inserisci il path dove scrivere i file di output (CLEAN/REJECT/QC)",
                DEFAULT_TEST_DATA_DIR,
            )
            out_dir.mkdir(parents=True, exist_ok=True)

            base = input_csv.name
            output_csv = out_dir / f"CLEAN_{base}"
            rejected_csv = out_dir / f"REJECT_{base}"
            report_csv = out_dir / f"QC_{base}"

            print("\n===== RIEPILOGO =====")
            print(f"Input CSV : {input_csv}")
            print(f"Cleaned   : {output_csv}")
            print(f"Rejected  : {rejected_csv}")
            print(f"Report    : {report_csv}")
            print("=====================\n")

    # -------------------------
    # Run QC
    # -------------------------
    df = load_csv(input_csv, sep=args.sep)
    cleaned, rejected, stats = run_qc(df, selected_rules=selected_rules)

    # Export sempre i tre file (CLEAN/REJECT/QC)
    export_csv(cleaned, output_csv, sep=args.sep)
    export_csv(rejected, rejected_csv, sep=args.sep)

    import pandas as pd

    rep = pd.DataFrame(
        [
            ("total_rows", stats.total_rows),
            ("kept_rows", stats.kept_rows),
            ("rejected_rows", stats.rejected_rows),
            ("rejected_pct", round(stats.rejected_pct, 4)),
        ],
        columns=["metric", "value"],
    )
    for k, v in stats.per_rule_rejections.items():
        rep.loc[len(rep)] = (f"rejected_by_{k}", v)
    export_csv(rep, report_csv, sep=args.sep)

    # Sanity check: clean + reject deve = total
    if (len(cleaned) + len(rejected)) != stats.total_rows:
        print(
            "[QC][WARN] Incoerenza conteggi: "
            f"clean({len(cleaned)}) + reject({len(rejected)}) != total({stats.total_rows})"
        )

    print(
        f"[QC] Input={stats.total_rows} "
        f"Kept={stats.kept_rows} "
        f"Rejected={stats.rejected_rows} "
        f"({stats.rejected_pct:.2f}%)"
    )
    print(f"[QC] Cleaned:  {output_csv}")
    print(f"[QC] Rejected: {rejected_csv}")
    print(f"[QC] Report:   {report_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
