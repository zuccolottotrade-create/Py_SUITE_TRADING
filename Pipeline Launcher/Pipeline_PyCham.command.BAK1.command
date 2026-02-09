#!/bin/zsh
set -euo pipefail

# I/O sempre su TTY (robusto contro moduli che rompono stdin)
exec 3</dev/tty 4>/dev/tty

say() { echo "$@"; }
pause() { say ""; read -r "REPLY?Premi INVIO per continuare..." <&3; }
tty_sane() { stty sane 2>/dev/null || true; }
tty_sane

# ============================================================
# Pipeline_PyCham.command (LAUNCHER UNIFICATO)
#
# MENU PRINCIPALE (2 sezioni):
#   A) Esecuzione Pipeline (estrazione_pro -> QC -> KPI -> Run -> Report)
#   B) Strategy Creator (classificazione -> map-strategies -> build-config)
#
# Requisiti:
# - Dopo ogni modulo (anche singolo) torna al menu principale
# - Mantiene moduli pipeline interattivi (PIPELINE_MODE=0)
# - Strategy Creator usa la venv del repo strategy_creator e produce log per ogni run
# ============================================================

# ============================================================
# ROOT DETECTION ROBUSTA
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

find_root() {
  local d="$SCRIPT_DIR"
  for _ in {1..6}; do
    if [[ -d "$d/_data" ]]; then
      echo "$d"
      return 0
    fi
    d="$(cd "$d/.." && pwd)"
  done
  return 1
}

PY_SUITE_ROOT="$(find_root || true)"
if [[ -z "${PY_SUITE_ROOT:-}" ]]; then
  say "❌ Impossibile determinare PY_SUITE_ROOT partendo da: $SCRIPT_DIR"
  say "   Atteso trovare la cartella _data in uno dei parent."
  pause
  exit 1
fi
export PY_SUITE_ROOT

# ============================================================
# Logging
# ============================================================
LOG_DIR="$PY_SUITE_ROOT/_logs"
mkdir -p "$LOG_DIR"

# ============================================================
# Helpers
# ============================================================
require_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    say "❌ File non trovato: $f"
    return 1
  fi
  return 0
}

require_dir() {
  local d="$1"
  if [[ ! -d "$d" ]]; then
    say "❌ Cartella non trovata: $d"
    return 1
  fi
  return 0
}

# ============================================================
# Runner per moduli pipeline (script .command)
# ============================================================
run_cmd_file() {
  local label="$1"
  local cmd="$2"
  local mode="${3:-0}"   # 0=interattivo, 1=pipeline



  tty_sane
  say "======================================"
  say " $label"
  say "======================================"
  require_file "$cmd" || { pause; return 1; }

  if [[ "$mode" == "1" ]]; then
  # Pipeline: NON puliamo le variabili, abilitiamo PIPELINE_MODE=1
  PIPELINE_MODE="1" "$cmd"
else
  # Interattivo: pulizia variabili pipeline e PIPELINE_MODE=0
  if [[ "$mode" == "1" ]]; then
  # Pipeline: NON pulire, abilita PIPELINE_MODE=1
  PIPELINE_MODE="1" "$cmd"
else
  # Interattivo: pulizia variabili pipeline + PIPELINE_MODE=0
  unset PY_SUITE_SIGNAL_INPUT_CSV
  unset PY_SUITE_SIGNAL_INPUT
  unset PY_SUITE_SIGNAL_LATEST
  unset PIPELINE_MODE
  PIPELINE_MODE="0" "$cmd"
fi


  tty_sane
  say ""
  if [[ $rc -ne 0 ]]; then
    say "❌ FALLITO (rc=$rc): $label"
  else
    say "✅ OK: $label"
  fi
  pause
  return $rc
}

# ============================================================
# Runner per Strategy Creator (python -m ... con venv + log)
# ============================================================
STRATEGY_REPO="$PY_SUITE_ROOT/5. Strategy Creator/strategy_creator"
STRATEGY_VENV="$STRATEGY_REPO/.venv"

run_strategy_step() {
  local title="$1"
  shift

  tty_sane
  say "======================================"
  say " $title"
  say "======================================"

  require_dir "$STRATEGY_REPO" || { pause; return 1; }
  require_dir "$STRATEGY_VENV" || { say "   (Atteso venv in: $STRATEGY_VENV)"; pause; return 1; }

  local log_file="$LOG_DIR/launcher_strategy_${(%)$(date +%Y%m%d_%H%M%S)}.log"
  say "Log: $log_file"
  say ""

  (
    set -euo pipefail
    # attiva venv e posizionati nel repo
    source "$STRATEGY_VENV/bin/activate"
    cd "$STRATEGY_REPO"

    # esegui comando e logga tutto
    set +e
    "$@" 2>&1 | tee -a "$log_file"
    rc=${pipestatus[1]:-0}
    exit $rc
  )
  local rc=$?

  tty_sane
  say ""
  if [[ $rc -ne 0 ]]; then
    say "❌ FALLITO (rc=$rc): $title"
    say "   Vedi log: $log_file"
  else
    say "✅ OK: $title"
    say "   Log: $log_file"
  fi
  pause
  return $rc
}

# ============================================================
# Moduli Pipeline (path attesi nel repo)
# ============================================================
run_estrazione_pro() {
  run_cmd_file "A1 - estrazione_pro" \
    "$PY_SUITE_ROOT/1. estrazione_pro/estrazione_pro.command"
}

run_controllo_coerenza() {
  run_cmd_file "A2 - Controllo_coerenza_dati" \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/Controllo_coerenza_dati.command"
}

run_pykpi_calcolo() {
  run_cmd_file "A3 - PyKPI_calcolo" \
    "$PY_SUITE_ROOT/2. PyKPI_calcolo/PyKPI_calcolo.command"
}

run_strategia() {
  run_cmd_file "A4 - Run_strategia" \
    "$PY_SUITE_ROOT/3. Run_strategia/Run_strategia.command"
}

run_report() {
  run_cmd_file "A5 - Report_strategia" \
    "$PY_SUITE_ROOT/4. REPORT strategia/Report_strategia.command"
}

run_pipeline_completa() {
  tty_sane
  say "======================================"
  say " A6 - PIPELINE COMPLETA (INTERATTIVA)"
  say "======================================"
  say "Eseguirò i moduli in sequenza; ogni modulo rimane interattivo."
  pause

  run_estrazione_pro || return 1
  run_controllo_coerenza || return 1
  run_pykpi_calcolo || return 1
  run_strategia || return 1
  run_report || return 1
  return 0

  run_pipeline_completa_pipeline() {
  tty_sane
  say "======================================"
  say " A7 - PIPELINE COMPLETA (PIPELINE_MODE=1)"
  say "======================================"
  say "Eseguirò i moduli in sequenza in modalità pipeline (non interattiva)."
  pause

  run_cmd_file "A1 - estrazione_pro"     "$PY_SUITE_ROOT/1. estrazione_pro/estrazione_pro.command" 1 || return 1
  run_cmd_file "A2 - Controllo_coerenza" "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/Controllo_coerenza_dati.command" 1 || return 1
  run_cmd_file "A3 - PyKPI_calcolo"      "$PY_SUITE_ROOT/2. PyKPI_calcolo/PyKPI_calcolo.command" 1 || return 1
  run_cmd_file "A4 - Run_strategia"      "$PY_SUITE_ROOT/3. Run_strategia/Run_strategia.command" 1 || return 1
  run_cmd_file "A5 - Report_strategia"   "$PY_SUITE_ROOT/4. REPORT strategia/Report_Strategia.command" 1 || return 1

  return 0
}

}

# ============================================================
# Strategy Creator (menu B)
# ============================================================
run_classificazione_operativa() {
  run_strategy_step "B1 - Classificazione Operativa (CLEAN_ -> CLASSIFICAZIONE_)" \
    python -m strategy_creator.cli
}

run_map_strategies() {
  run_strategy_step "B2 - Strategy Mapper (map-strategies)" \
    python -m strategy_mapper.cli map-strategies --interactive
}

run_build_config() {
  run_strategy_step "B3 - Build Config (RULES_ -> config_strategy_)" \
    python -m strategy_mapper.cli build-config --interactive
}

run_wizard_regime_filter() {
  run_strategy_step "B4 - Regime Filter Wizard (apply + report)" \
    python3 "$PY_SUITE_ROOT/shared/wizard_regime_filter.py"


}


run_strategy_completa() {
  tty_sane
  say "======================================"
  say " B4 - STRATEGY CREATOR COMPLETA (B1->B3)"
  say "======================================"
  pause

  run_classificazione_operativa || return 1
  run_map_strategies || return 1
  run_build_config || return 1
  return 0
}

# ============================================================
# MENU PRINCIPALE (A + B)
# ============================================================
menu() {
  while true; do
    tty_sane
    say ""
    say "============================================================"
    say " LAUNCHER UNIFICATO - Py_SUITE_TRADING"
    say " ROOT: $PY_SUITE_ROOT"
    say "============================================================"
    say ""
    say "---------------------  A. ESECUZIONE PIPELINE  ---------------------"
    say "  1) A1  estrazione_pro"
    say "  2) A2  Controllo_coerenza_dati"
    say "  3) A3  PyKPI_calcolo"
    say "  4) A4  Run_strategia"
    say "  5) A5  Report_strategia"
    say "  6) A6  Pipeline completa (A1->A5)"
    
    say ""
    say "---------------------  B. STRATEGY CREATOR  ------------------------"
    say "  7) B1  Classificazione Operativa (CLEAN_ -> CLASSIFICAZIONE_)"
    say "  8) B2  Strategy Mapper (map-strategies)"
    say "  9) B3  Build Config (build-config)"
    say " 10) B4  Regime Filter Wizard (apply + report)"
    say " 11) B5  Strategy Creator completo (B1->B3)"
    say ""
    say "  0) Esci"
    say "--------------------------------------------------------------------"
    read -r "CHOICE?Seleziona un'opzione: " <&3

    case "$CHOICE" in
      1)  run_estrazione_pro ;;
      2)  run_controllo_coerenza ;;
      3)  run_pykpi_calcolo ;;
      4)  run_strategia ;;
      5)  run_report ;;
      6)  run_pipeline_completa ;;
      7)  run_classificazione_operativa ;;
      8)  run_map_strategies ;;
      9)  run_build_config ;;
      10) run_wizard_regime_filter ;;
      11) run_strategy_completa ;;
      0)  say "👋 Fine."; exit 0 ;;
      *)  say "Scelta non valida."; pause ;;
    esac
  done
}

menu


