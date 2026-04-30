# Trakkr — Architecture Reference

This document is the single source of truth for how Trakkr is laid out: where the data starts, how it becomes a forecast, how the API serves that forecast, and how the frontend consumes it. It exists so anyone can audit the codebase end-to-end without grep-archaeology.

---

## 1. The 30-second mental model

```
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│ Public open data     │ ─▶ │ Monthly model run    │ ─▶ │ Static forecast CSVs │
│ (MTA, NYPD, Ridrshp) │    │ (analysis/*.py)      │    │ (data/artifacts/...) │
└──────────────────────┘    └──────────────────────┘    └──────────┬───────────┘
                                                                   │
                                                                   ▼
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│ Static frontend      │ ◀─ │ Live MTA feeds       │ ◀─ │ FastAPI service      │
│ (frontend/*.html)    │    │ (ENE XML + GTFS-RT)  │    │ (api/app.py)         │
└──────────────────────┘    └──────────────────────┘    └──────────────────────┘
```

Three big ideas:

1. **Forecasts are precomputed**, not generated on request. The pipeline runs offline, writes CSVs to a versioned `data/artifacts/<run_id>/` directory, and updates a pointer file (`data/artifacts/latest/forecast.json`).
2. **The API is mostly a CSV-reader plus live-feed proxy**. It does not load ML models at request time — it reads the pre-published CSVs and bundles in live MTA status.
3. **The frontend is fully static HTML.** No build step. The dashboard talks to the API; every other page is plain HTML/Tailwind.

---

## 2. Data flow, in detail

### 2.1 Inputs (raw open data)

| File | Source | Coverage |
|---|---|---|
| `data/raw/elevator_escalator_availability_fresh.csv` | MTA Open Data (rc78-7x78) | 2015–2026-03 |
| `data/raw/nypd_transit_crime.csv` + `nypd_crime_2025_2026.csv` | NYPD via NYC Open Data (5uac-w243) | 2020–Q1 2026 |
| `data/raw/station_ridership_2025.csv` | MTA Hourly Ridership (5wq4-mkjj) | 11 months averaged |
| `data/raw/station_coords.json` | Project-curated (371 stations) | Static |

### 2.2 Cleaning + feature engineering

```
analysis/clean_data.py   →  data/clean/{elevator,crime,ridership}_clean.csv
analysis/features.py     →  shared feature builders (lag, rolling, velocity, severity)
analysis/data_contracts.py →  fail-fast schema/range validation
```

`features.py` is imported by `model1.py`, `model2.py`, `predict_2027_2029.py`, and `backtest_models.py`. It defines:
- `build_elevator_features(df)` — 34 features per unit-month (lags, rolls, unit stats, station stats, time-since-improvement)
- `build_crime_base_features(df)` — severity-weighted, ridership-normalized station-month features
- `cold_start_backfill(...)` — fills NaN lags for new units with borough+type averages
- `pick_recall_threshold(probs, y_true, target=0.95)` — picks decision threshold targeting given recall

### 2.3 Training

```
analysis/model1.py   →  data/artifacts/<run_id>/model1_elevator.joblib
                    →  data/artifacts/<run_id>/model1_escalator.joblib
                    →  threshold_model1_{elevator,escalator}.json
analysis/model2.py   →  data/artifacts/<run_id>/model2.joblib
                    →  threshold_model2.json
```

Both use XGBoost. Splits: `train ≤ 2024 / val = 2024 / test ≥ 2025`. Targets:
- **Model 1** — `needs_service_next` (any unscheduled outage or entrapment in next 30 days)
- **Model 2** — `is_hotspot` (top-5-by-density within borough that month)

### 2.4 Forecast (the artifact riders actually see)

```
analysis/predict_2027_2029.py
  loads:  joblib models from latest run
  emits:  forecast_model1_2027_2029.csv  ← per-unit, per-month service probability + severity tier
          forecast_model2_2027_2029.csv  ← per-station, per-month hotspot probability + label
  writes: data/artifacts/<new_run_id>/  (versioned)
  updates: data/artifacts/latest/forecast.json  (pointer)
```

`forecast.json` shape:

```json
{
  "pipeline_name": "forecast",
  "latest_run_id": "forecast_20260429T010414Z_84aa9a3a",
  "latest_run_dir": "/abs/path/to/data/artifacts/forecast_20260429T010414Z_84aa9a3a",
  "updated_at": "2026-04-29T01:04:14+00:00"
}
```

> **Cross-machine note.** `latest_run_dir` is absolute on the machine that wrote it. The API now resolves both the recorded path *and* a fallback rebuilt from `latest_run_id` against the running deployment's `BASE`, so a pointer written on a dev machine still works after deploy.

### 2.5 Backtest + drift + quality gate

```
analysis/backtest_models.py    →  rolling walk-forward, prints recall per fold (24 folds)
analysis/drift_monitor.py      →  compares last N months against baseline; ✅/⚠️/❌ report
ops/quality_gate.py            →  asserts forecast CSVs meet sanity bounds before publish
ops/monitor_pipeline.py        →  freshness + run-health checks
ops/rollback_latest.py         →  flips `latest/forecast.json` to a prior run
```

### 2.6 Pipeline orchestration

`ops/run_mvp_pipeline.sh` is the canonical end-to-end:

```
clean_data → model1 → model2 → backtest_models → predict_2027_2029
           → quality_gate → add_forecast_sheets
```

Everything else (`run_model1.sh`, `run_models.sh`, etc.) is a single-step convenience runner used during development.

---

## 3. Backend — `api/app.py`

A single 700-line FastAPI module. No database. Reads the latest forecast CSVs and several MTA feeds, returns JSON.

### 3.1 Endpoints

| Path | Purpose |
|---|---|
| `GET /health` | Liveness + readiness. `forecast.ready=true` confirms artifacts are loadable. |
| `GET /v1/snapshots/latest` | Which forecast run is currently live. |
| `GET /v1/stations` | All station names (optional `?q=` substring filter). |
| `GET /v1/lookup?address=...` | Geocode an address → nearest station → full Trakkr report. |
| `GET /v1/station?name=...` | Direct station-name lookup → same report shape. |
| `GET /v1/forecast/model1` | Raw elevator-forecast rows, filtered by min probability. |
| `GET /v1/forecast/model2` | Raw safety-forecast rows, filtered by min probability. |
| `GET /v1/forecast/summary` | Aggregate stats for the current forecast snapshot. |
| `GET /v1/mta/elevator-status` | Live ENE XML feeds — current outages + upcoming + ADA flag. |
| `GET /v1/mta/line-status` | Aggregated GTFS-RT subway alerts, one row per line, with worst-status priority. |
| `GET /v1/mta/service-alerts` | Raw alert list (optionally filtered by line). |

### 3.2 External services

| Service | Purpose | Auth |
|---|---|---|
| Mapbox Geocoding v6 | Address → lat/lon | Public `pk.` token (`MAPBOX_TOKEN` env) |
| MTA ENE XML | Equipment inventory + current outages + planned outages | None |
| MTA GTFS-RT (camsys subway-alerts) | Live subway alerts | None |

### 3.3 Caching

| Cache | TTL | Where |
|---|---|---|
| Equipment inventory XML | 120s | `_EQUIP_CACHE` |
| Current outages XML | 120s | `_OUTAGE_CACHE` |
| Upcoming outages XML | 120s | `_UPCOMING_CACHE` |
| GTFS-RT subway alerts | 60s | `_ALERTS_CACHE` |
| Equipment-code → station map | process lifetime (`@lru_cache`) | `_load_equipment_map` |
| Station coordinates JSON | process lifetime (`@lru_cache`) | `_load_station_coords` |

Note: caches are module-level dicts and **not thread-safe**. Concurrent requests during a cache miss can trigger duplicate upstream fetches but won't corrupt state. Acceptable for current scale; revisit if traffic > ~10 rps.

### 3.4 Error policy

All upstream failures (Mapbox, MTA) return **HTTP 502 with a generic message**. URLs and tokens are never echoed to the client (this used to leak in 502 detail strings; fixed in this audit).

---

## 4. Frontend — `frontend/`

Static HTML + Tailwind CDN + vanilla JS. **No build step.**

| Page | Purpose |
|---|---|
| `index.html` | Marketing home + address search → redirects to dashboard |
| `dashboard.html` | The actual product: enter an address, render the full station report (Leaflet map + Trakkr verdict + live MTA panels) |
| `trakkrecord.html` | Long-form pitch for the prediction engine; "for builders" section |
| `blog.html` + `blog-*.html` (×6) | Blog index + standalone articles |
| `about.html` | Story / values |
| `faq.html` | Q&A |
| `feedback.html` | Web3Forms-backed contact form (no email exposed in HTML) |
| `privacy.html` / `legal.html` / `accessibility.html` | Required legal pages |
| `robots.txt`, `sitemap.xml` | Discoverability |

Shared chrome injected on every page:
- Fixed top header (Trakkr logo + nav + Check-a-Station CTA)
- Footer (Trakkr brand block + Pages / Data / Legal columns)
- Floating bottom-left **Feedback** pill → `feedback.html`
- Buy Me a Coffee widget (bottom-right)

### 4.1 Frontend → backend contract

The dashboard fetches from the FastAPI service. The base URL needs to be set per environment. Today it's hardcoded to `http://localhost:8000` in `dashboard.html` — see Phase 4 deploy notes for production wiring.

---

## 5. Dead / stale code (flag for cleanup)

These were touched during model evolution and may no longer be load-bearing. Audit before deleting:

| File | Status | Notes |
|---|---|---|
| `analysis/build_models.py` | **Stale** | Older combined trainer (`v4`). Superseded by separate `model1.py` + `model2.py`. Confirm no script references it before deleting. |
| `analysis/build_excel.py` + `add_forecast_sheets.py` + `add_model_sheets.py` | **Stale at deploy time** | These build the `.xlsx` audit workbook. Useful for hackathon presentation, not for running prod. Safe to leave — they don't run on every pipeline. |
| `analysis/analyze.py` | **Auxiliary** | Generates exploratory charts in `charts/`. Not on the production path. |
| `run_model.sh` / `run_models.sh` / `run_model1.sh` / `run_model2.sh` / `run_forecast_2027_2029.sh` | **Convenience scripts** | All of these are single-step wrappers used during development. The canonical pipeline is `ops/run_mvp_pipeline.sh`. Reduce to one in a future cleanup. |

---

## 6. Environment + configuration

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `MAPBOX_TOKEN` | `api/app.py` (geocoder), `frontend/dashboard.html` (tiles) | A `pk.` token committed in code | OK to commit a public Mapbox token; restrict allowed referrers in Mapbox dashboard for production |
| `CORS_ORIGINS` | `api/app.py` | `localhost:8765,localhost:5173,127.0.0.1:8765` | Comma-separated. Set to live frontend origin at deploy. |
| `MTA_API_KEY` | reserved | `""` | Today's feeds are public; reserved for future authenticated endpoints |

See `.env.example` at the repo root for the canonical template.

---

## 7. Known limitations / future work

- **Tailwind CDN in production.** Pages load ~3 MB of unused Tailwind on every visit. For perf, compile a per-page stylesheet via Tailwind CLI before public launch.
- **No rate limiting** on the API. A bot can hammer `/v1/lookup` and burn through Mapbox geocoding quota. Add `slowapi` or platform-level rate limiting before opening to the public internet.
- **Caches are not shared across instances.** If you scale the backend horizontally, each replica fetches MTA feeds independently. Move caches to Redis if that becomes a problem.
- **Forecast is monthly.** New stations or units commissioned mid-month won't appear until the next pipeline run.

---

*Last reviewed: 2026-04-30.*
