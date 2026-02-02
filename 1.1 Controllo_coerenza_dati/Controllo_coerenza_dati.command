#!/bin/bash
# ==========================================================
# Controllo_coerenza_dati.command
# Avvio stand-alone modulo 1.1 Controllo_coerenza_dati
# (INTERATTIVO) + Root/Data-dir robusti
# ==========================================================

set -u

clear
echo "=============================================="
echo " Avvio Controllo_coerenza_dati (stand-alone)"
echo "=============================================="
echo

# --- Directory del file .command ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Root detection robusta: risali finché trovi marker repo ---
ROOT_CANDIDATE="$SCRIPT_DIR"
for _ in 1 2 3 4; do
  if [[ -d "$ROOT_CANDIDATE/_data" || -d "$ROOT_CANDIDATE/.git" || -d "$ROOT_CANDIDATE/1.1 Controllo_coerenza_dati" ]]; then
    break
  fi
  ROOT_CANDIDATE="$(cd "$ROOT_CANDIDATE/.." && pwd)"
done

export PY_SUITE_ROOT="$ROOT_CANDIDATE"

# Data dir default (se non già impostata dall’esterno)
: "${PY_SUITE_DATA_DIR:=$PY_SUITE_ROOT/_data/Test Data}"
export PY_SUITE_DATA_DIR

# --- Entra nella directory del modulo ---
cd "$SCRIPT_DIR" || exit 1

# --- Attiva virtualenv locale ---
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "ERRORE: virtualenv .venv non trovato."
  echo "Crea il venv prima di lanciare il modulo."
  read -r -p "Premi INVIO per tornare..."
  exit 1
fi

echo "Python in uso:"
python3 --version
echo

echo "----------------------------------------------"
echo " Avvio controllo coerenza dati"
echo "----------------------------------------------"
echo "[INFO] PY_SUITE_ROOT=$PY_SUITE_ROOT"
echo "[INFO] PY_SUITE_DATA_DIR=$PY_SUITE_DATA_DIR"
echo

python3 -m controllo_coerenza.cli
EXIT_CODE=$?

echo
echo "----------------------------------------------"
echo " Fine esecuzione (exit code = $EXIT_CODE)"
echo "----------------------------------------------"
echo

read -r -p "Premi INVIO per tornare..."
exit $EXIT_CODE
