#!/bin/zsh
set -e

echo "======================================"
echo " Avvio applicazione PyKPI_calcolo"
echo "======================================"
echo

# Vai nella directory del progetto
cd "$(dirname "$0")"

# Controllo virtual environment
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERRORE: virtual environment (.venv) non trovata."
  echo "Contatta il supporto tecnico."
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  exit 1
fi

# Attiva virtualenv (facoltativo, ma ok)
source ".venv/bin/activate"

echo "PATH attuale: $PATH"
echo "which python: $(which python || echo 'NON TROVATO')"
echo

# Usa esplicitamente l'interprete del venv
PY=".venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "ERRORE: interprete Python del virtualenv non trovato: $PY"
  echo "Contatta il supporto tecnico."
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  exit 1
fi

echo "Python in uso:"
"$PY" -V
echo

echo "Avvio calcolo KPI..."
echo
"$PY" main.py

echo
echo "Elaborazione KPI terminata."
read -n 1 -s -r -p "Premi un tasto per chiudere..."

