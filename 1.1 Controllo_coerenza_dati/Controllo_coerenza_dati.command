#!/bin/bash
# ==========================================================
# Controllo_coerenza_dati.command
# Avvio stand-alone modulo 1.1 Controllo_coerenza_dati
# ==========================================================

clear
echo "=============================================="
echo " Avvio Controllo_coerenza_dati (stand-alone)"
echo "=============================================="
echo

# --- Directory del file .command ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Entra nella directory del modulo ---
cd "$SCRIPT_DIR" || exit 1

# --- Attiva virtualenv locale ---
if [ -d ".venv" ]; then
  source .venv/bin/activate
else
  echo "ERRORE: virtualenv .venv non trovato."
  echo "Crea il venv prima di lanciare il modulo."
  read -p "Premi INVIO per passare al PROSSIMO MODULO..."
  exit 1
fi

echo "Python in uso:"
python3 --version
echo

# --- Avvio modulo ---
echo "----------------------------------------------"
echo " Avvio controllo coerenza dati"
echo "----------------------------------------------"
echo

python3 -m controllo_coerenza.cli

EXIT_CODE=$?

echo
echo "----------------------------------------------"
echo " Fine esecuzione (exit code = $EXIT_CODE)"
echo "----------------------------------------------"
echo

read -p "Premi INVIO per passare al PROSSIMO MODULO il terminale..."
exit $EXIT_CODE
