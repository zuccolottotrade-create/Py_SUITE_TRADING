from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass
class RunInputs:
    kpi_csv: Path
    strategy_xlsx: Path
    timeframe: Optional[str] = None


VALID_TIMEFRAMES = {"30m", "1h", "1d", "1w"}


def _find_project_root(start: Optional[Path] = None) -> Path:
    here = (start or Path(__file__).resolve()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "_data").exists():
            return candidate
    raise FileNotFoundError("Project root non trovato: manca directory _data")


def resolve_project_dirs(project_root: Optional[Path] = None) -> tuple[Path, Path]:
    root = _find_project_root(project_root)
    kpi_dir = root / "_data" / "Test Data"
    config_dir = root / "_data" / "config_strategia"
    return kpi_dir, config_dir


def list_kpi_files(kpi_dir: Path) -> list[Path]:
    if not kpi_dir.exists():
        return []
    files = [
        p for p in kpi_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".csv" and p.name.startswith("KPI_")
    ]
    return sorted(files, key=lambda p: (-p.stat().st_mtime, p.name.lower()))


def list_strategy_files(config_dir: Path) -> list[Path]:
    if not config_dir.exists():
        return []
    files = [
        p for p in config_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".xlsx"
        and p.name.startswith("config_strategy")
        and not p.name.startswith("~$")
    ]
    return sorted(files, key=lambda p: (-p.stat().st_mtime, p.name.lower()))


def choose_from_menu(files: list[Path], title: str) -> Path:
    if not files:
        raise FileNotFoundError(f"Nessun file disponibile per: {title}")

    while True:
        print()
        print("=" * 80)
        print(title)
        print("=" * 80)
        for idx, path in enumerate(files, start=1):
            print(f"{idx:2d}) {path.name}")
        raw = input("Seleziona numero: ").strip()

        if not raw:
            print("Scelta vuota. Riprova.")
            continue
        if not raw.isdigit():
            print("Inserire un numero valido.")
            continue

        index = int(raw)
        if index < 1 or index > len(files):
            print(f"Scelta fuori range: 1..{len(files)}")
            continue

        return files[index - 1]


def validate_kpi_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"File KPI non trovato: {path}"
    if path.suffix.lower() != ".csv":
        return False, f"Estensione KPI non valida: {path.name}"
    if not path.name.startswith("KPI_"):
        return False, f"Il file KPI deve iniziare con 'KPI_': {path.name}"

    # Lettura robusta: i file KPI della suite usano normalmente ';'
    # e possono contenere numeri EU con virgola decimale.
    # Qui dobbiamo solo validare l'header, non caricare tutto il dataset.
    read_attempts = [
        {"sep": ";", "engine": "python", "nrows": 5},
        {"sep": ",", "engine": "python", "nrows": 5},
        {"sep": None, "engine": "python", "nrows": 5},
    ]

    last_exc = None
    df = None

    for kwargs in read_attempts:
        try:
            df = pd.read_csv(path, **kwargs)
            break
        except Exception as exc:
            last_exc = exc

    if df is None:
        return False, f"Errore lettura CSV KPI: {last_exc}"

    required_cols = {"REGIME_L1_CODE"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return False, f"Manca colonna KPI obbligatoria: {', '.join(missing)}"

    return True, "OK"


def validate_strategy_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"File strategy non trovato: {path}"
    if path.suffix.lower() != ".xlsx":
        return False, f"Estensione strategy non valida: {path.name}"

    expected_sheets = {"CONDITIONS", "ENUMS", "KPI_COLUMNS", "TUNING"}
    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
        sheet_names = set(xl.sheet_names)
    except Exception as exc:
        return False, f"Errore apertura Excel strategy: {exc}"

    missing = sorted(expected_sheets - sheet_names)
    if missing:
        return False, f"Mancano fogli strategy: {', '.join(missing)}"

    return True, "OK"


def prompt_timeframe(default: Optional[str] = None) -> str:
    allowed = sorted(VALID_TIMEFRAMES)
    default_value = default if default in VALID_TIMEFRAMES else "1h"

    while True:
        print()
        raw = input(f"Timeframe [{default_value}] ({', '.join(allowed)}): ").strip()
        value = raw or default_value
        if value in VALID_TIMEFRAMES:
            return value
        print(f"Timeframe non valido: {value}")


def confirm_summary(inputs: RunInputs) -> bool:
    print()
    print("=" * 80)
    print("RIEPILOGO INPUT")
    print("=" * 80)
    print(f"KPI CSV       : {inputs.kpi_csv}")
    print(f"Strategy XLSX : {inputs.strategy_xlsx}")
    print(f"Timeframe     : {inputs.timeframe or '-'}")
    raw = input("Confermi? [Y/n]: ").strip().lower()
    return raw in ("", "y", "yes", "s", "si")


def prompt_run_inputs(
    project_root: Optional[Path] = None,
    ask_timeframe: bool = True,
    default_timeframe: Optional[str] = "1h",
) -> RunInputs:
    kpi_dir, config_dir = resolve_project_dirs(project_root=project_root)

    if not kpi_dir.exists():
        raise FileNotFoundError(f"Directory KPI non trovata: {kpi_dir}")
    if not config_dir.exists():
        raise FileNotFoundError(f"Directory strategy non trovata: {config_dir}")

    while True:
        kpi_files = list_kpi_files(kpi_dir)
        if not kpi_files:
            raise FileNotFoundError(f"Nessun file KPI_*.csv trovato in: {kpi_dir}")

        while True:
            kpi_path = choose_from_menu(kpi_files, "Seleziona file KPI")
            ok, msg = validate_kpi_file(kpi_path)
            if ok:
                print(f"✓ KPI valido: {kpi_path.name}")
                break
            print(f"✗ {msg}")

        strategy_files = list_strategy_files(config_dir)
        if not strategy_files:
            raise FileNotFoundError(
                f"Nessun file config_strategy*.xlsx trovato in: {config_dir}"
            )

        while True:
            strategy_path = choose_from_menu(strategy_files, "Seleziona config strategy")
            ok, msg = validate_strategy_file(strategy_path)
            if ok:
                print(f"✓ Strategy valida: {strategy_path.name}")
                break
            print(f"✗ {msg}")

        timeframe = None
        if ask_timeframe:
            timeframe = prompt_timeframe(default=default_timeframe)

        inputs = RunInputs(
            kpi_csv=kpi_path,
            strategy_xlsx=strategy_path,
            timeframe=timeframe,
        )

        if confirm_summary(inputs):
            return inputs

        print("Selezione annullata. Ripetere la scelta dei file.")


if __name__ == "__main__":
    selected = prompt_run_inputs()
    print()
    print("INPUT SELEZIONATI")
    print(selected)