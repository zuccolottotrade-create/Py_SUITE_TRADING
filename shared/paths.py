from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str) -> Path | None:
    v = os.getenv(name, "").strip()
    return Path(v) if v else None


def get_suite_root() -> Path:
    root = _env_path("PY_SUITE_ROOT")
    if root:
        return root
    return Path(__file__).resolve().parents[1]


def get_data_dir() -> Path:
    dd = _env_path("PY_SUITE_DATA_DIR")
    if dd:
        return dd
    return get_suite_root() / "_data" / "Test Data"


SUITE_ROOT = get_suite_root()
DATA_DIR = get_data_dir()

def get_kpi_config_dir() -> Path:
    v = os.getenv("PY_SUITE_KPI_CONFIG_DIR", "").strip()
    if v:
        return Path(v)

    # KPI Configurazione è in root (non sotto _data)
    return get_suite_root() / "KPI Configurazione"


KPI_CONFIG_DIR = get_kpi_config_dir()
