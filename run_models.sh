#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "==> Creating virtual environment (.venv) if needed"
python3 -m venv .venv

echo "==> Activating virtual environment"
source .venv/bin/activate

echo "==> Upgrading pip"
python3 -m pip install --upgrade pip

echo "==> Installing dependencies"
python3 -m pip install -r requirements.txt

echo "==> Running Model 1"
python3 analysis/model1.py

echo "==> Running Model 2"
python3 analysis/model2.py

echo "==> Done. Both model scripts completed."
