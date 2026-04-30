# NYC Subway Safety Analysis: 2020–2026

A data-driven investigation into subway rider safety in New York City, built for the CUNY AI Innovation Hackathon 2026.

## The Story

COVID-19 collapsed ridership. Crime spiked. Elevator outages persisted. And the system is still catching up.
This project quantifies the post-pandemic subway safety crisis using three primary datasets.

## Datasets

| File | Source | Coverage |
|------|--------|----------|
| `data/raw/mta_daily_ridership.csv` | MTA / data.ny.gov | Mar 2020 – 2025 |
| `data/raw/nypd_transit_crime.csv` | NYPD / NYC Open Data | 2020 – 2024 |
| `data/raw/elevator_escalator_availability.csv` | MTA / data.ny.gov | 2015 – 2025 |

## Structure

```
├── data/
│   ├── raw/          # Original downloaded datasets
│   └── clean/        # Cleaned, filtered datasets ready for analysis
├── analysis/         # Python analysis scripts
├── charts/           # All generated visualizations
└── README.md
```

## Key Safety Dimensions Analyzed

1. **Ridership Recovery** — Post-pandemic return to pre-COVID baseline
2. **Transit Crime Trends** — Felony, misdemeanor, and violation breakdowns by year and borough
3. **Crime by Offense Type** — What crimes dominate the subway system
4. **Elevator & Escalator Failures** — Unscheduled outages and entrapments over time
5. **Borough-Level Risk** — Where riders are most at risk

## How to Run

### 1) Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### 3) Prepare cleaned datasets (if not already prepared)

```bash
python3 analysis/clean_data.py
```

### 4) Run general analysis pipeline (optional)

```bash
python3 analysis/analyze.py
```

### 5) Run each model separately

```bash
python3 analysis/model1.py
python3 analysis/model2.py
```

### 5b) Run one model independently via runner scripts

```bash
./run_model1.sh
./run_model2.sh
```

Run a model multiple times (example: twice):

```bash
./run_model1.sh --times 2
./run_model2.sh --times 2
```

Or use the generic selector:

```bash
./run_model.sh model1 --times 2
./run_model.sh model2 --times 1
```

### 6) (Optional) Run combined model script

```bash
python3 analysis/build_models.py
```

### 7) Run backtesting reliability harness

```bash
python3 analysis/backtest_models.py
```

### 8) Generate forecast snapshot with scenario mode

```bash
python3 analysis/predict_2027_2029.py --scenario baseline
python3 analysis/predict_2027_2029.py --scenario conservative
python3 analysis/predict_2027_2029.py --scenario stress
```

### 9) Run full MVP pipeline (clean -> train -> backtest -> forecast -> quality gate)

```bash
./ops/run_mvp_pipeline.sh
```

### 10) Serve read-only snapshot API

```bash
uvicorn api.app:app --reload --port 8000
```

See API details in `docs/api_contract.md`.

### 11) Monitoring and rollback operations

```bash
python3 ops/monitor_pipeline.py
python3 ops/rollback_latest.py --pipeline forecast --run-id <run_id>
```

See operational guidance in `docs/ops_runbook.md`.

### Notes for XGBoost on macOS

- If `xgboost` fails with a `libomp.dylib` error, install OpenMP runtime (for example using Homebrew `libomp`) and rerun.
- The standalone model scripts include a fallback to `HistGradientBoostingClassifier` when XGBoost cannot load, so the scripts can still run.

## Team

Built by Dennis Comandante — CUNY AI Innovation Hackathon 2026
