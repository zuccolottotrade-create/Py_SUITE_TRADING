#!/bin/zsh
set -e

echo "======================================"
echo " Avvio applicazione estrazione_pro"
echo "======================================"
echo

cd "$(dirname "$0")"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERRORE: virtual environment (.venv) non trovata."
  echo "Contatta il supporto tecnico."
  echo
  read -n 1 -s -r -p "Premi un tasto per uscire..."
  exit 1
fi

source .venv/bin/activate

echo "Python in uso:"
python -V
echo

python -m pip install -e . >/dev/null 2>&1 || true

echo "Avvio estrazione_pro..."
echo
python -m estrazione.cli.estrazione_pro

echo
echo "Esecuzione terminata."
read -n 1 -s -r -p "Premi un tasto per chiudere..."
