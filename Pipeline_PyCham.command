#!/bin/zsh
set -euo pipefail
# I/O sempre su TTY (robusto contro moduli che rompono stdin)
exec 3</dev/tty 4>/dev/tty

tty_sane() { stty sane 2>/dev/null || true; }
tty_sane



# ============================================================
# Pipeline_PyCham.command
# - Default: INTERATTIVO (PIPELINE_MODE=0)
# - Per NON interattivo: export PIPELINE_MODE=1
# - Menu: avvio singolo modulo o pipeline completa
# - Moduli: estrazione_pro -> Controllo_coerenza_dati -> PyKPI_calcolo -> Run_strategia -> Report_strategia
# - Auto-seleziona ultimo SIGNAL_*.csv e lo passa al report via PY_SUITE_SIGNAL_INPUT_CSV (solo PIPELINE_MODE=1)
# ============================================================

say() { echo "$@"; }

# --------- Root detection ---------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PY_SUITE_ROOT="$SCRIPT_DIR"

# --------- Modalità pipeline ---------
PIPELINE_MODE="${PIPELINE_MODE:-0}"

# --------- Default data dir (comune tipico) ---------
DEFAULT_DATA_DIR="$PY_SUITE_ROOT/_data/Test Data"

# --------- KPI config dir: autodetect (root e poi _data) ---------
if [[ -d "$PY_SUITE_ROOT/KPI Configurazione" ]]; then
  DEFAULT_KPI_CONFIG_DIR="$PY_SUITE_ROOT/KPI Configurazione"
elif [[ -d "$PY_SUITE_ROOT/_data/KPI Configurazione" ]]; then
  DEFAULT_KPI_CONFIG_DIR="$PY_SUITE_ROOT/_data/KPI Configurazione"
else
  DEFAULT_KPI_CONFIG_DIR="$PY_SUITE_ROOT/KPI Configurazione"
fi

# --------- Helpers ---------
pick_first_existing_file() {
  for f in "$@"; do
    if [[ -f "$f" ]]; then
      echo "$f"
      return 0
    fi
  done
  echo "$1"
}

latest_file_matching() {
  local dir="$1"
  local pattern="$2"
  local files=("$dir"/$pattern(N))
  if (( ${#files[@]} == 0 )); then
    echo ""
    return 0
  fi
  local sorted=("$dir"/$pattern(OmN))
  echo "$sorted[1]"
}

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
    say "❌ Directory non trovata: $d"
    return 1
  fi
  return 0
}

tty_sane() {
  # Ripristina TTY se un modulo ha lasciato il terminale "sporco"
  stty sane 2>/dev/null || true
}




# --------- Defaults (usati SOLO se PIPELINE_MODE=1) ---------
DEFAULT_ESTRAZIONE_OUTPUT_DIR="$DEFAULT_DATA_DIR"
DEFAULT_KPI_DATA_DIR="$DEFAULT_DATA_DIR"

# KPI Excel: prima il file reale in "KPI Configurazione"
DEFAULT_KPI_CONFIG_XLSX="$(pick_first_existing_file \
  "$DEFAULT_KPI_CONFIG_DIR/indicator_defaults.xlsx" \
  "$DEFAULT_KPI_CONFIG_DIR/config_kpi.xlsx" \
  "$PY_SUITE_ROOT/2. PyKPI_calcolo/config/indicator_defaults.xlsx" \
  "$PY_SUITE_ROOT/2. PyKPI_calcolo/config/config_kpi.xlsx" \
)"

# Strategie: nuovo standard in _data/config_strategia
DEFAULT_STRATEGY_DIR="$PY_SUITE_ROOT/_data/config_strategia"
mkdir -p "$DEFAULT_STRATEGY_DIR"

DEFAULT_STRATEGY_XLSX="$(pick_first_existing_file \
  "$DEFAULT_STRATEGY_DIR/config_strategy_v2.xlsx" \
  "$DEFAULT_STRATEGY_DIR/config_strategy.xlsx" \
  "$PY_SUITE_ROOT/3. Run_strategia/config_strategy_v2.xlsx" \
  "$PY_SUITE_ROOT/3. Run_strategia/config_strategy.xlsx" \
  "$PY_SUITE_ROOT/3. Run_strategia/config/config_strategy_v2.xlsx" \
  "$PY_SUITE_ROOT/3. Run_strategia/config/config_strategy.xlsx" \
)"

DEFAULT_STRATEGY_DATA_DIR="$DEFAULT_DATA_DIR"
DEFAULT_REPORTS_DIR="$DEFAULT_DATA_DIR"

say "======================================"
say " Pipeline Py_SUITE_TRADING"
say " ROOT: $PY_SUITE_ROOT"
say " PIPELINE_MODE=$PIPELINE_MODE"
say "======================================"
say ""

# ============================================================
# ENV (effective)
# - Se PIPELINE_MODE=1: forza default e zero prompt (per automazione)
# - Se PIPELINE_MODE=0: NON forza nulla (moduli restano interattivi)
# ============================================================
if [[ "$PIPELINE_MODE" == "1" ]]; then
  export PY_SUITE_ESTRAZIONE_OUTPUT_DIR="$DEFAULT_ESTRAZIONE_OUTPUT_DIR"
  export PY_SUITE_KPI_DATA_DIR="$DEFAULT_KPI_DATA_DIR"
  export PY_SUITE_KPI_CONFIG_XLSX="$DEFAULT_KPI_CONFIG_XLSX"
  export PY_SUITE_KPI_CONFIG_DIR="$DEFAULT_KPI_CONFIG_DIR"

  export PY_SUITE_STRATEGY_DIR="$DEFAULT_STRATEGY_DIR"
  export PY_SUITE_STRATEGY_XLSX="$DEFAULT_STRATEGY_XLSX"

  export PY_SUITE_STRATEGY_DATA_DIR="$DEFAULT_STRATEGY_DATA_DIR"
  export PY_SUITE_REPORTS_DIR="$DEFAULT_REPORTS_DIR"

  say "ℹ️ Modalità NON interattiva: uso defaults (PIPELINE_MODE=1)"
else
  say "ℹ️ Modalità INTERATTIVA: i moduli gestiscono i prompt (PIPELINE_MODE=0)"
fi
say ""

# --------- Sanity checks (solo cose strutturali) ---------
# In interattivo NON obblighiamo file config/strategy: li gestiranno i moduli.
if ! require_dir "$PY_SUITE_ROOT"; then exit 1; fi

if [[ "$PIPELINE_MODE" == "1" ]]; then
  if ! require_dir "$PY_SUITE_ESTRAZIONE_OUTPUT_DIR"; then exit 1; fi
  if ! require_dir "$PY_SUITE_KPI_DATA_DIR"; then exit 1; fi
  if ! require_dir "$PY_SUITE_KPI_CONFIG_DIR"; then exit 1; fi
  if ! require_file "$PY_SUITE_KPI_CONFIG_XLSX"; then exit 1; fi

  if ! require_dir "$PY_SUITE_STRATEGY_DIR"; then exit 1; fi
  if ! require_file "$PY_SUITE_STRATEGY_XLSX"; then exit 1; fi

  if ! require_dir "$PY_SUITE_STRATEGY_DATA_DIR"; then exit 1; fi
  if ! require_dir "$PY_SUITE_REPORTS_DIR"; then exit 1; fi
fi

if [[ "$PIPELINE_MODE" == "1" ]]; then
  say "=============================="
  say " ENV (effective)"
  say "=============================="
  say "[PIPE] PY_SUITE_ESTRAZIONE_OUTPUT_DIR=$PY_SUITE_ESTRAZIONE_OUTPUT_DIR"
  say "[PIPE] PY_SUITE_KPI_DATA_DIR=$PY_SUITE_KPI_DATA_DIR"
  say "[PIPE] PY_SUITE_KPI_CONFIG_DIR=$PY_SUITE_KPI_CONFIG_DIR"
  say "[PIPE] PY_SUITE_KPI_CONFIG_XLSX=$PY_SUITE_KPI_CONFIG_XLSX"
  say "[PIPE] PY_SUITE_STRATEGY_DIR=$PY_SUITE_STRATEGY_DIR"
  say "[PIPE] PY_SUITE_STRATEGY_XLSX=$PY_SUITE_STRATEGY_XLSX"
  say "[PIPE] PY_SUITE_STRATEGY_DATA_DIR=$PY_SUITE_STRATEGY_DATA_DIR"
  say "[PIPE] PY_SUITE_REPORTS_DIR=$PY_SUITE_REPORTS_DIR"
  say "=============================="
  say ""
fi

# ============================================================
# FUNZIONI: i moduli
# ============================================================

run_estrazione_pro() {
  say "======================================"
  say " STEP 1/5 - estrazione_pro"
  say "======================================"

  if [[ "$PIPELINE_MODE" == "1" ]]; then
    export PY_SUITE_DATA_DIR="$PY_SUITE_ESTRAZIONE_OUTPUT_DIR"
  fi

  local ESTRAZIONE_CMD="$PY_SUITE_ROOT/1. estrazione_pro/estrazione_pro.command"
  require_file "$ESTRAZIONE_CMD" || return 1
  PIPELINE_MODE="$PIPELINE_MODE" "$ESTRAZIONE_CMD"
}

run_controllo_coerenza() {
  say "======================================"
  say " STEP 2/5 - Controllo_coerenza_dati"
  say "======================================"

  local QC_CMD
  QC_CMD="$(pick_first_existing_file \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/controllo_coerenza.command" \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/Controllo_coerenza.command" \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/controllo_coerenza_dati.command" \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/Controllo_coerenza_dati.command" \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/controllo_coerenza.py" \
    "$PY_SUITE_ROOT/1.1 Controllo_coerenza_dati/scripts/controllo_coerenza.py" \
  )"

  require_file "$QC_CMD" || return 1

  if [[ "$PIPELINE_MODE" == "1" ]]; then
    export PY_SUITE_DATA_DIR="$PY_SUITE_ESTRAZIONE_OUTPUT_DIR"
  fi

  if [[ "$QC_CMD" == *.command ]]; then
    PIPELINE_MODE="$PIPELINE_MODE" "$QC_CMD"
  else
    PIPELINE_MODE="$PIPELINE_MODE" python3 "$QC_CMD"
  fi
}

run_pykpi() {
  say "======================================"
  say " STEP 3/5 - PyKPI_calcolo"
  say "======================================"

  local KPI_CMD="$PY_SUITE_ROOT/2. PyKPI_calcolo/PyKPI_calcolo.command"
  local KPI_MAIN="$PY_SUITE_ROOT/2. PyKPI_calcolo/main.py"

  if [[ "$PIPELINE_MODE" == "1" ]]; then
    export PY_SUITE_DATA_DIR="$PY_SUITE_KPI_DATA_DIR"
    export PY_SUITE_KPI_CONFIG_XLSX="$PY_SUITE_KPI_CONFIG_XLSX"
    export PY_SUITE_KPI_CONFIG_DIR="$PY_SUITE_KPI_CONFIG_DIR"
  fi

  if [[ -f "$KPI_CMD" ]]; then
    PIPELINE_MODE="$PIPELINE_MODE" "$KPI_CMD"
  else
    require_file "$KPI_MAIN" || return 1
    PIPELINE_MODE="$PIPELINE_MODE" python3 "$KPI_MAIN" --config-xlsx "${PY_SUITE_KPI_CONFIG_XLSX:-}"
  fi
}

run_strategia() {
  say "======================================"
  say " STEP 4/5 - Run_strategia"
  say "======================================"

  local RUNSTRAT_CMD="$PY_SUITE_ROOT/3. Run_strategia/Run_strategia.command"
  local RUNSTRAT_PY="$PY_SUITE_ROOT/3. Run_strategia/run_strategia.py"

  if [[ "$PIPELINE_MODE" == "1" ]]; then
    export PY_SUITE_DATA_DIR="$PY_SUITE_STRATEGY_DATA_DIR"
    export PY_SUITE_STRATEGY_DIR="$PY_SUITE_STRATEGY_DIR"
    export PY_SUITE_STRATEGY_FILE="$PY_SUITE_STRATEGY_XLSX"
  fi

  if [[ -f "$RUNSTRAT_CMD" ]]; then
    PIPELINE_MODE="$PIPELINE_MODE" "$RUNSTRAT_CMD"
  else
    require_file "$RUNSTRAT_PY" || return 1
    PIPELINE_MODE="$PIPELINE_MODE" python3 "$RUNSTRAT_PY"
  fi

  if [[ "$PIPELINE_MODE" == "1" ]]; then
    local LATEST_SIGNAL
    LATEST_SIGNAL="$(latest_file_matching "$PY_SUITE_STRATEGY_DATA_DIR" "SIGNAL_*.csv")"
    if [[ -z "$LATEST_SIGNAL" ]]; then
      say "❌ Nessun file SIGNAL_*.csv trovato in: $PY_SUITE_STRATEGY_DATA_DIR"
      return 1
    fi
    export PY_SUITE_SIGNAL_INPUT_CSV="$LATEST_SIGNAL"
    say "[PIPE] PY_SUITE_SIGNAL_INPUT_CSV=$PY_SUITE_SIGNAL_INPUT_CSV"
  fi
}

run_report() {
  say "======================================"
  say " STEP 5/5 - Report_strategia"
  say "======================================"

  local REPORT_PY="$PY_SUITE_ROOT/4. REPORT strategia/scripts/report_strategia.py"
  require_file "$REPORT_PY" || return 1
  PIPELINE_MODE="$PIPELINE_MODE" python3 "$REPORT_PY"
}

run_pipeline_completa() {
  run_estrazione_pro
  run_controllo_coerenza
  run_pykpi
  run_strategia
  run_report

  say ""
  say "======================================"
  say " ✅ PIPELINE COMPLETATA"
  say "======================================"
  if [[ "$PIPELINE_MODE" == "1" ]]; then
    say "SIGNAL usato: ${PY_SUITE_SIGNAL_INPUT_CSV:-<unset>}"
    say "Report dir:   ${PY_SUITE_REPORTS_DIR:-<unset>}"
  fi
  say ""
}

run_strategy_qc_preflight() {
  clear
  say "======================================"
  say " Strategy QC Preflight (stand-alone)"
  say "======================================"
  say " ROOT: $PY_SUITE_ROOT"
  say " Strategy dir: ${PY_SUITE_STRATEGY_DIR:-$PY_SUITE_ROOT/_data/config_strategia}"
  say "======================================"
  say ""

  local STRATEGY_DIR="${PY_SUITE_STRATEGY_DIR:-$PY_SUITE_ROOT/_data/config_strategia}"
  local QC_PY="$PY_SUITE_ROOT/3. Run_strategia/strategy_qc.py"

  require_dir "$STRATEGY_DIR" || return 1
  require_file "$QC_PY" || return 1

  # ------------------------------------------------------------
  # Selezione OBBLIGATORIA file strategia (.xlsx)
  # ------------------------------------------------------------
  local -a files


  files=("$STRATEGY_DIR"/*.xlsx(N))
  # escludi i lock file di Excel (~$...)
  local -a filtered
  filtered=()
  local f
  for f in "${files[@]}"; do
      [[ "${f:t}" == "~$"* ]] && continue
      filtered+=("$f")
  done
  files=("${filtered[@]}")





  if (( ${#files[@]} == 0 )); then
    say "❌ Nessun file .xlsx trovato in:"
    say "   $STRATEGY_DIR"
    say ""
    say "Premi INVIO per tornare al menu..."
    read -r
    return 0
  fi

  say "File strategia disponibili (.xlsx):"
  say "Directory: $STRATEGY_DIR"
  say ""
  local i=1
  for f in "${files[@]}"; do
    say "  $i) ${f:t}"
    ((i++))
  done
  say ""
  printf "Seleziona numero (0=annulla): "
  local sel
  read -r sel

  if [[ -z "${sel:-}" || "$sel" == "0" ]]; then
    say ""
    say "Annullato."
    say "Premi INVIO per tornare al menu..."
    read -r
    return 0
  fi

  if ! [[ "$sel" =~ '^[0-9]+$' ]] || (( sel < 1 || sel > ${#files[@]} )); then
    say ""
    say "❌ Selezione non valida: '$sel'"
    say "Premi INVIO per tornare al menu..."
    read -r
    return 0
  fi

  local STRAT_PATH="${files[$sel]}"

  if [[ -z "${files[$sel]-}" ]]; then
    say "❌ Selezione non valida: $sel"
    say "Premi INVIO per tornare al menu..."
    read -r
    return 0
  fi

local STRAT_PATH="${files[$sel]}"




  say ""
  say "--------------------------------------"
  say " Strategia selezionata: ${STRAT_PATH:t}"
  say "--------------------------------------"
  say ""

  # ------------------------------------------------------------
  # Esecuzione QC (SEMPRE fallback KPI_COLUMNS)
  # ------------------------------------------------------------
  local rc=0
  set +e

  say "--------------------------------------"
  say " QC in esecuzione..."
  say "--------------------------------------"
  say ""

  python3 "$QC_PY" --strategy-xlsx "$STRAT_PATH"
  rc=$?

  set -e
  tty_sane

  if [[ $rc -eq 0 ]]; then
    say "✅ Strategy QC terminato (OK/WARN)."
  else
    say "⚠️ Strategy QC terminato con codice=$rc (non blocco il menu)."
  fi

  say ""
  say "Premi INVIO per tornare al menu..."
  read -r
  return 0
}





# ============================================================
# MENU LOOP (semplice, ritorna sempre al menu)
# ============================================================
while true; do
clear
  echo "======================================"
  echo " Pipeline Py_SUITE_TRADING"
  echo "======================================"
  echo " 1) Estrazione dati"
  echo " 2) Controllo coerenza dati"
  echo " 3) PyKPI_calcolo"
  echo " 4) Run_strategia"
  echo " 5) Report_Strategia"
  echo " 6) Pipeline completa"
  echo " 7) Strategy QC Preflight"
  echo " 8) Esci"
   echo "======================================"
  echo ""

  tty_sane
  print -u4 -n "Seleziona opzione: "
  IFS= read -r choice <&3 || choice=""

  case "$choice" in
    1) run_estrazione_pro ;;
    2) run_controllo_coerenza ;;
    3) run_pykpi ;;
    4) run_strategia ;;
    5) run_report ;;
    6) run_pipeline_completa ;;
    7) run_strategy_qc_preflight ;;
    8) say "Uscita."; exit 0 ;;
    *) say "Scelta non valida." ;;
  esac

  say ""
  tty_sane
  print -u4 -n "Premi INVIO per tornare al menu..."
  IFS= read -r _ <&3 || true
  echo ""
  echo ""
done

