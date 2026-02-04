from pathlib import Path

# ============================================================
# Project root
# ============================================================
# Struttura attesa:
# <SUITE_ROOT>/
# ├── shared/
# │   └── paths.py   <-- questo file
# ├── _data/
# │   └── config_KPI/
# ├── 2. PyKPI_calcolo/
# └── ...
#
SUITE_ROOT = Path(__file__).resolve().parents[1]

# ============================================================
# Data directories
# ============================================================
DATA_DIR = (SUITE_ROOT / "_data").resolve()

# ============================================================
# KPI configuration (UNICA FONTE DI VERITÀ)
# ============================================================
# Directory contenente:
# - indicator_defaults.xlsx
# - KPI_defaults.xlsx
# - eventuali altri Excel di configurazione KPI
#
KPI_CONFIG_DIR = (DATA_DIR / "config_KPI").resolve()

# ============================================================
# (eventuali altri path di progetto possono stare sotto)
# ============================================================

