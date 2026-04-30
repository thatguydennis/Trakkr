#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -q -r requirements.txt

echo "==> Clean data"
python3 analysis/clean_data.py

echo "==> Train/evaluate model1"
python3 analysis/model1.py

echo "==> Train/evaluate model2"
python3 analysis/model2.py

echo "==> Backtest reliability"
python3 analysis/backtest_models.py

echo "==> Generate forecast snapshot"
python3 analysis/predict_2027_2029.py --scenario baseline

echo "==> Run quality gate"
python3 ops/quality_gate.py \
  --model1-csv data/clean/forecast_model1_2027_2029.csv \
  --model2-csv data/clean/forecast_model2_2027_2029.csv

echo "==> Update workbook forecast sheets"
python3 analysis/add_forecast_sheets.py

echo "==> Pipeline completed successfully"
