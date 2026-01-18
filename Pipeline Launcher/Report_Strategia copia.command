#!/bin/bash
set -euo pipefail

# =========================
# CONFIG: ADATTA QUESTI PATH
# =========================

# 1) Cartella del progetto (dove c'è scripts/report_strategia.py)
PROJECT_DIR="/Users/claudio 1/PycharmProjects/REPORT strategia"

# 2) Python da usare (consigliato: venv del progetto)
#    Esempio venv: "$PROJECT_DIR/.venv/bin/python"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

# 3) Script da lanciare
SCRIPT_PATH="$PROJECT_DIR/scripts/report_strategia.py"

# 4) (Opzionale) argomenti CLI per il tuo script
ARGS=""

# =========================
# RUN
# =========================
cd "$PROJECT_DIR"


export PYTHONPATH="$PROJECT_DIR"
export PYTHONUNBUFFERED=1

"$PYTHON_BIN" "$SCRIPT_PATH" $ARGS

echo "== PyCham / Report Strategia =="
echo "Project: $PROJECT_DIR"
echo "Python : $PYTHON_BIN"
echo "Script : $SCRIPT_PATH"
echo ""


echo ""
echo "Fatto. Premi INVIO per chiudere..."
read -r
