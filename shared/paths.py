# /Users/claudio 1/Py_SUITE_TRADING/shared/paths.py
from __future__ import annotations

import os
from pathlib import Path

# Suite root = cartella che contiene "shared"
SUITE_ROOT = Path(__file__).resolve().parents[1]

def _default_data_dir() -> Path:
    """
    Default data dir: <SUITE_ROOT>/_data
    (coerente con naming Py_SUITE_TRADING)
    """
    return (SUITE_ROOT / "_data").resolve()

# 1) Se esiste una variabile d'ambiente esplicita, usala
#    (questa è la forma più pulita in pipeline)
_env = os.environ.get("PY_SUITE_DATA_DIR") or os.environ.get("PY_SUITE_TRADING_DATA_DIR")

# 2) DATA_DIR finale
DATA_DIR = str(Path(_env).expanduser().resolve()) if _env else str(_default_data_dir())

def _default_kpi_config_dir() -> Path:
    """
    Directory di configurazione KPI (xlsx/template).
    Default: <SUITE_ROOT>/2. PyKPI_calcolo/config
    """
    return (SUITE_ROOT / "2. PyKPI_calcolo" / "config").resolve()

_env_cfg = os.environ.get("PY_KPI_CONFIG_DIR") or os.environ.get("KPI_CONFIG_DIR")

KPI_CONFIG_DIR = str(Path(_env_cfg).expanduser().resolve()) if _env_cfg else str(_default_kpi_config_dir())

