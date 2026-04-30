#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -q -r requirements.txt
python3 analysis/predict_2027_2029.py
