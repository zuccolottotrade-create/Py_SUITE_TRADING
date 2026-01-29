#!/bin/bash
set -euo pipefail

# ============================================================
# Launcher Strategy Pipeline (MENU FIRST)
# 1) Classificazione Operativa
# 2) Strategy mapping (map-strategies)
# 3) Rules generation (build-rules)
# 4) Pipeline completa (1->2->3)
# Uscita: Ctrl+C
# ============================================================

BASE_SUITE="/Users/claudio 1/Py_SUITE_TRADING"
BASE_REPO="/Users/claudio 1/Py_SUITE_TRADING/5. Strategy Creator/strategy_creator"
VENV="$BASE_REPO/.venv"

LOG_DIR="$BASE_SUITE/_logs"
mkdir -p "$LOG_DIR"

# --- Exit handling: Ctrl+C
trap 'echo ""; echo "⛔ Interrotto (Ctrl+C). Uscita."; echo ""; exit 130' INT

# --- Activate venv
if [[ ! -d "$VENV" ]]; then
  echo "❌ Venv non trovata: $VENV"
  exit 1
fi

# shellcheck disable=SC1090
source "$VENV/bin/activate"
cd "$BASE_REPO"

run_step () {
  local title="$1"
  shift

  # nuovo log per ogni esecuzione “operativa”
  LOG_FILE="$LOG_DIR/launcher_strategy_pipeline_$(date +%Y%m%d_%H%M%S).log"

  echo "============================================================" | tee -a "$LOG_FILE"
  echo " Launcher Strategy Pipeline"                                 | tee -a "$LOG_FILE"
  echo "============================================================" | tee -a "$LOG_FILE"
  echo "Suite : $BASE_SUITE"                                        | tee -a "$LOG_FILE"
  echo "Repo  : $BASE_REPO"                                         | tee -a "$LOG_FILE"
  echo "Venv  : $VENV"                                              | tee -a "$LOG_FILE"
  echo "Log   : $LOG_FILE"                                          | tee -a "$LOG_FILE"
  echo "------------------------------------------------------------" | tee -a "$LOG_FILE"
  echo "▶ $title"                                                   | tee -a "$LOG_FILE"
  echo "Command: $*"                                                | tee -a "$LOG_FILE"
  echo "------------------------------------------------------------" | tee -a "$LOG_FILE"

  set +e
  "$@" 2>&1 | tee -a "$LOG_FILE"
  local rc=${PIPESTATUS[0]}
  set -e

  if [[ $rc -ne 0 ]]; then
    echo "" | tee -a "$LOG_FILE"
    echo "❌ Step FALLITO (rc=$rc): $title" | tee -a "$LOG_FILE"
    echo "   Vedi log: $LOG_FILE"           | tee -a "$LOG_FILE"
    return $rc
  fi

  echo "✅ Step OK: $title" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  return 0
}

while true; do
  echo "============================================================"
  echo " MENU - Strategy Pipeline"
  echo "============================================================"
  echo "  1) Classificazione operativa (CLEAN_ -> CLASSIFICAZIONE_)"
  echo "  2) Strategy mapping        (CLASSIFICAZIONE_ -> STRATEGIA_)"
  echo "  3) Rules generation        (STRATEGIA_ -> RULES_)"
  echo "  4) Pipeline completa (1 -> 2 -> 3)"
  echo "  5) Apri cartella log"
  echo "  Ctrl+C) Esci"
  echo ""

  read -r -p "Scelta [1-5] (Invio=menu): " choice
  choice="${choice:-0}"
  echo ""

  case "${choice}" in
    0)
      # Invio: torna al menu
      ;;
    1)
      run_step "Classificazione Operativa" python -m strategy_creator.cli || true
      ;;
    2)
      run_step "Strategy Mapper - map-strategies" python -m strategy_mapper.cli map-strategies --interactive || true
      ;;
    3)
      run_step "Strategy Mapper - build-rules" python -m strategy_mapper.cli build-rules --interactive || true
      ;;
    4)
      run_step "1/3 Classificazione Operativa" python -m strategy_creator.cli || true
      run_step "2/3 Strategy Mapper - map-strategies" python -m strategy_mapper.cli map-strategies --interactive || true
      run_step "3/3 Strategy Mapper - build-rules" python -m strategy_mapper.cli build-rules --interactive || true
      ;;
    5)
      open "$LOG_DIR" >/dev/null 2>&1 || true
      ;;
    *)
      echo "Scelta non valida. Inserisci 1-5 (Ctrl+C per uscire)."
      ;;
  esac

  echo ""
done
