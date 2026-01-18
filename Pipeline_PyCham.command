#!/bin/bash
set -euo pipefail

# ==========================================================
# Py_SUITE_TRADING – environment
# ==========================================================
export PY_SUITE_ROOT="/Users/claudio 1/Py_SUITE_TRADING"

# Alias legacy (compatibilità con script esistenti)
export PYCHAM_SUITE_DIR="$PY_SUITE_ROOT"
export SUITE_DIR="$PY_SUITE_ROOT"

# Dati e configurazioni sotto _data
export PY_SUITE_DATA_DIR="$PY_SUITE_ROOT/_data/Test Data"
export PY_SUITE_KPI_CONFIG_DIR="$PY_SUITE_ROOT/_data/KPI Configurazione"

# (opzionale ma utile) Directory strategie (ora dentro la suite)
export PY_SUITE_STRATEGY_DIR="$PY_SUITE_ROOT/config_strategy"

# Import path suite (shared + moduli dei singoli step)
BASE_PYTHONPATH="$PY_SUITE_ROOT:$PY_SUITE_ROOT/4. REPORT strategia:$PY_SUITE_ROOT/2. PyKPI_calcolo:$PY_SUITE_ROOT/3. Run_strategia"
if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="$BASE_PYTHONPATH:$PYTHONPATH"
else
  export PYTHONPATH="$BASE_PYTHONPATH"
fi

# ==========================================================
# INTERATTIVO: forziamo PIPELINE_MODE=0 per tutti gli step
# ==========================================================
export PIPELINE_MODE=0

# Gestione CTRL+C (SIGINT)
on_interrupt() {
  echo ""
  echo "❌ PIPELINE interrotta dall'utente (CTRL+C)."
  echo "Uscita."
  exit 130
}
trap on_interrupt INT

echo "[PIPELINE] DATA_DIR=$PY_SUITE_DATA_DIR"
echo "[PIPELINE] KPI_CONFIG_DIR=$PY_SUITE_KPI_CONFIG_DIR"
echo "[PIPELINE] STRATEGY_DIR=$PY_SUITE_STRATEGY_DIR"
echo "[PIPELINE] MODE: PIPELINE_MODE=$PIPELINE_MODE (TUTTO INTERATTIVO)"
echo ""

ts() { date "+%Y-%m-%d %H:%M:%S"; }

echo "========================================"
echo "        PYCHAM PIPELINE AVVIATA"
echo "========================================"
echo "SUITE: $PYCHAM_SUITE_DIR"
echo ""

run_step () {
  local step_name="$1"
  local cmd_path="$2"

  echo "----------------------------------------"
  echo "$(ts) | $step_name"
  echo "$cmd_path"
  echo "----------------------------------------"

  if [ ! -f "$cmd_path" ]; then
    echo "❌ ERRORE: file non trovato: $cmd_path"
    exit 1
  fi
  if [ ! -x "$cmd_path" ]; then
    echo "❌ ERRORE: file non eseguibile (fai chmod +x): $cmd_path"
    exit 1
  fi

  "$cmd_path"

  echo "✅ COMPLETATO: $step_name"
  echo ""
}

run_step "STEP 1/4 - estrazione_pro (interattivo)" "$SUITE_DIR/1. estrazione_pro/estrazione_pro.command"

echo "[CHECK] Import shared.paths (KPI_CONFIG_DIR) prima dello STEP 2..."
PYTHON_BIN="$PY_SUITE_ROOT/.venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi
"$PYTHON_BIN" -c "from shared.paths import KPI_CONFIG_DIR; print('[CHECK] KPI_CONFIG_DIR =', KPI_CONFIG_DIR)"
echo ""

run_step "STEP 2/4 - PyKPI_calcolo (interattivo)" "$SUITE_DIR/2. PyKPI_calcolo/PyKPI_calcolo.command"
run_step "STEP 3/4 - Run_strategia (interattivo)" "$SUITE_DIR/3. Run_strategia/Run_strategia.command"
run_step "STEP 4/4 - Report_Strategia (interattivo)" "$SUITE_DIR/4. REPORT strategia/Report_Strategia.command"

echo "========================================"
echo "        PIPELINE COMPLETATA"
echo "========================================"
echo ""
echo "Premi INVIO per chiudere..."
read -r
exit 0
