#!/bin/zsh
set -e

echo "======================================"
echo " Avvio applicazione Run_strategia"
echo "======================================"
echo

# Vai nella directory del progetto
cd "$(dirname "$0")"

# Controllo file essenziali
if [[ ! -f "run_strategia.py" ]]; then
  echo "ERRORE: file non trovato: run_strategia.py"
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  echo
  exit 1
fi

if [[ ! -f "load_engine.py" ]]; then
  echo "ERRORE: file non trovato: load_engine.py"
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  echo
  exit 1
fi

# Controllo virtual environment
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERRORE: virtual environment (.venv) non trovata."
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  echo
  exit 1
fi

# Attiva virtualenv
source ".venv/bin/activate"

# Usa esplicitamente il Python del venv
PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERRORE: interprete Python del virtualenv non trovato."
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  echo
  exit 1
fi

echo "Python in uso:"
"$PY" -V
echo

echo "Avvio Run_strategia..."
echo
"$PY" run_strategia.py

echo
echo "Esecuzione terminata."
read -n 1 -s -r -p "Premi un tasto per chiudere..."
echo
