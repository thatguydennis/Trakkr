"""
predict_2027_2029.py
Forecast-style predictions for 2027-2029 using saved trained models.

Loads model artifacts written by model1.py and model2.py, derives future
feature rows from the latest observed history, and outputs risk predictions.
Run model1.py and model2.py before running this script.
"""

from __future__ import annotations

import argparse
import json
import os
import warnings

import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "data", "clean")
OUT1  = os.path.join(CLEAN, "forecast_model1_2027_2029.csv")
OUT2  = os.path.join(CLEAN, "forecast_model2_2027_2029.csv")

from artifacts import copy_to_run_dir, create_run_context, update_latest_pointer, write_run_metadata
from data_contracts import CRIME_CONTRACT, ELEVATOR_CONTRACT, require_columns, validate_dataframe_contract
from features import (
    CRIME_FEATS,
    ELEVATOR_FEATS,
    HAS_XGBOOST,
    build_crime_features,
    build_elevator_features,
    classify_severity,
)

M1_TRAIN_CUTOFF = 2024
M2_TRAIN_CUTOFF = 2024

SCENARIO_MULTIPLIERS = {
    "baseline":    1.0,
    "conservative": 0.95,
    "stress":      1.10,
}


# ─────────────────────────────────────────────────────────────────────────────
# Artifact loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_model_artifact(pipeline_name: str, model_filename: str, threshold_filename: str):
    pointer_path = os.path.join(BASE, "data", "artifacts", "latest", f"{pipeline_name}.json")
    if not os.path.exists(pointer_path):
        raise RuntimeError(
            f"No saved {pipeline_name} found. Run 'python analysis/{pipeline_name}.py' first."
        )
    with open(pointer_path) as fh:
        pointer = json.load(fh)
    run_dir = pointer["latest_run_dir"]
    model_path     = os.path.join(run_dir, model_filename)
    threshold_path = os.path.join(run_dir, threshold_filename)
    if not os.path.exists(model_path):
        raise RuntimeError(f"Artifact not found: {model_path}")
    model = joblib.load(model_path)
    with open(threshold_path) as fh:
        threshold = float(json.load(fh)["threshold"])
    return model, threshold


def confidence_bucket(probability: float) -> str:
    if probability >= 0.8: return "very_high"
    if probability >= 0.6: return "high"
    if probability >= 0.4: return "medium"
    if probability >= 0.2: return "low"
    return "very_low"


# ─────────────────────────────────────────────────────────────────────────────
# Model 1 forecast — separate elevator and escalator models
# ─────────────────────────────────────────────────────────────────────────────

def forecast_model1(scenario: str) -> pd.DataFrame:
    elev = pd.read_csv(os.path.join(CLEAN, "elevator_clean.csv"), parse_dates=["month"])
    validate_dataframe_contract(elev, ELEVATOR_CONTRACT)
    require_columns(
        elev,
        ["month", "year", "month_num", "equipment_code", "equipment_type", "borough",
         "am_peak_availability", "unscheduled_outages", "entrapments",
         "time_since_major_improvement"],
        "elevator_clean.csv",
    )

    elev_s, feats, _le_eq, _le_bor = build_elevator_features(elev, unit_stats_cutoff_year=M1_TRAIN_CUTOFF)

    # Keep the full feature frame (including the last month per unit where
    # needs_service_next is NaN) so that seed buffers include the most recent
    # observed data point.  Dropping NaN rows here would exclude the final
    # month for every unit, making the forecast start from one-month-stale data.
    elev_s_full = elev_s.copy()

    # Load per-type models
    models = {}
    for eq_type in ["Elevator", "Escalator"]:
        slug = eq_type.lower()
        models[eq_type] = _load_model_artifact(
            "model1", f"model1_{slug}.joblib", f"threshold_model1_{slug}.json"
        )

    future_months = pd.date_range("2027-01-01", "2029-12-01", freq="MS")
    mult = SCENARIO_MULTIPLIERS[scenario]
    rows = []

    for eq, g in elev_s_full.groupby("equipment_code"):
        g = g.sort_values("month")
        if len(g) < 6:
            continue

        last     = g.iloc[-1]
        eq_type  = str(last["equipment_type"])
        model, threshold = models.get(eq_type, models["Elevator"])

        # Rolling history buffers (pad to 6 with last known value)
        def _buf(col, n=6):
            vals = list(g[col].dropna().tail(n).values)
            while len(vals) < n:
                vals.insert(0, vals[0] if vals else 0.0)
            return vals

        avail_hist = _buf("am_peak_availability")
        unsch_hist = _buf("unscheduled_outages")
        trap_hist  = _buf("entrapments", n=3)
        svc_hist   = _buf("needs_service", n=6)    # current-month service flag
        sched_hist = _buf("scheduled_outages", n=3)
        tsmi       = float(last.get("time_since_major_improvement", 0) or 0)

        for dt in future_months:
            # Project next values using scenario multiplier
            unsch_next = max(0.0, float(unsch_hist[-1]) * mult)
            avail_next = max(0.0, min(100.0, float(avail_hist[-1]) * (2.0 - mult)))
            svc_next   = int(unsch_next > 0)

            feat_row = {
                "avail_lag1": avail_hist[-1], "avail_lag2": avail_hist[-2],
                "avail_lag3": avail_hist[-3], "avail_lag6": avail_hist[-6],
                "unsch_lag1": unsch_hist[-1], "unsch_lag2": unsch_hist[-2],
                "unsch_lag3": unsch_hist[-3], "unsch_lag6": unsch_hist[-6],
                "trap_lag1": trap_hist[-1], "trap_lag2": trap_hist[-2], "trap_lag3": trap_hist[-3],
                "svc_lag1": svc_hist[-1], "svc_lag2": svc_hist[-2],
                "svc_lag3": svc_hist[-3], "svc_lag6": svc_hist[-6],
                "sched_lag1": sched_hist[-1], "sched_lag3": sched_hist[-3],
                "avail_roll3": float(np.mean(avail_hist[-3:])),
                "avail_roll6": float(np.mean(avail_hist)),
                "unsch_roll3": float(np.mean(unsch_hist[-3:])),
                "unsch_roll6": float(np.mean(unsch_hist)),
                "svc_roll3":   float(np.mean(svc_hist[-3:])),
                "svc_roll6":   float(np.mean(svc_hist)),
                "unit_svc_rate":      float(last["unit_svc_rate"]),
                "unit_mean_outages":  float(last["unit_mean_outages"]),
                "unit_entrap_rate":   float(last["unit_entrap_rate"]),
                "unit_mean_avail":    float(last["unit_mean_avail"]),
                "stn_svc_rate":       float(last["stn_svc_rate"]) if pd.notna(last.get("stn_svc_rate")) else 0.0,
                "stn_mean_outages":   float(last["stn_mean_outages"]) if pd.notna(last.get("stn_mean_outages")) else 0.0,
                "time_since_major_improvement": tsmi,
                "eq_enc":    int(last["eq_enc"]),
                "bor_enc":   int(last["bor_enc"]),
                "month_num": int(dt.month),
                "year":      int(dt.year),
            }

            x     = pd.DataFrame([feat_row])[feats]
            p     = float(model.predict_proba(x)[:, 1][0])
            pred  = int(p >= threshold)
            sev   = classify_severity(
                np.array([p]), threshold, np.array([last["unit_entrap_rate"]])
            )[0]

            rows.append({
                "equipment_code":         eq,
                "equipment_type":         eq_type,
                "month":                  dt.strftime("%Y-%m-%d"),
                "predicted_service_prob": round(p, 6),
                "predicted_service_label": pred,
                "severity":               sev,
                "confidence_bucket":      confidence_bucket(p),
                "scenario_mode":          scenario,
            })

            # Advance history buffers
            avail_hist = (avail_hist + [avail_next])[-6:]
            unsch_hist = (unsch_hist + [unsch_next])[-6:]
            trap_hist  = (trap_hist  + [0.0])[-3:]
            svc_hist   = (svc_hist   + [float(svc_next)])[-6:]
            sched_hist = (sched_hist + [0.0])[-3:]
            tsmi      += 1.0

    out = pd.DataFrame(rows)
    out.to_csv(OUT1, index=False)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Model 2 forecast — crime hotspot with weighted score carry-forward
# ─────────────────────────────────────────────────────────────────────────────

def forecast_model2(scenario: str) -> pd.DataFrame:
    crime = pd.read_csv(os.path.join(CLEAN, "crime_clean.csv"), parse_dates=["date"])
    validate_dataframe_contract(crime, CRIME_CONTRACT)
    require_columns(
        crime, ["date", "year", "month", "station_name", "boro_nm", "ofns_desc"],
        "crime_clean.csv",
    )

    cm, feats, _le_bor = build_crime_features(crime, unit_stats_cutoff_year=M2_TRAIN_CUTOFF)
    m2, threshold = _load_model_artifact("model2", "model2.joblib", "threshold_model2.json")

    future_months = pd.date_range("2027-01-01", "2029-12-01", freq="MS")
    mult = SCENARIO_MULTIPLIERS[scenario]
    rows = []

    for stn, g in cm.groupby("station_name"):
        g = g.sort_values("month_dt")
        if len(g) < 6:
            continue

        last = g.iloc[-1]

        def _buf(col, n=6, default=0.0):
            vals = list(g[col].dropna().tail(n).values)
            while len(vals) < n:
                vals.insert(0, vals[0] if vals else default)
            return vals

        cnt_hist   = _buf("crime_count")
        score_hist = _buf("crime_score")
        hot_hist   = _buf("is_hotspot", n=12)
        rank_hist  = _buf("rank_pct")

        for dt in future_months:
            cnt_next   = max(0.0, float(cnt_hist[-1])   * mult)
            score_next = max(0.0, float(score_hist[-1]) * mult)
            rank_next  = float(rank_hist[-1])

            # Velocity features — computed from carry-forward buffers
            cnt_vel   = float(cnt_hist[-1])   - float(cnt_hist[-3])
            score_vel = float(score_hist[-1]) - float(score_hist[-3])
            cnt_pct_chg = cnt_vel / (abs(float(cnt_hist[-3])) + 1)

            feat_row = {
                "cnt_lag1": cnt_hist[-1], "cnt_lag2": cnt_hist[-2],
                "cnt_lag3": cnt_hist[-3], "cnt_lag6": cnt_hist[-6],
                "hotspot_lag1": hot_hist[-1], "hotspot_lag2": hot_hist[-2],
                "hotspot_lag3": hot_hist[-3], "hotspot_lag6": hot_hist[-6],
                "rank_lag1": rank_hist[-1], "rank_lag2": rank_hist[-2], "rank_lag3": rank_hist[-3],
                "roll_mean3": float(np.mean(cnt_hist[-3:])),
                "roll_mean6": float(np.mean(cnt_hist)),
                "roll_hot3":  float(np.mean(hot_hist[-3:])),
                "pct_hot_12m": float(np.mean(hot_hist)),
                "score_lag1": score_hist[-1], "score_lag2": score_hist[-2],
                "score_lag3": score_hist[-3], "score_lag6": score_hist[-6],
                "score_roll3": float(np.mean(score_hist[-3:])),
                "score_roll6": float(np.mean(score_hist)),
                "cnt_velocity_3m":   cnt_vel,
                "cnt_pct_chg_3m":    cnt_pct_chg,
                "score_velocity_3m": score_vel,
                "stn_mean":          float(last["stn_mean"]),
                "stn_median":        float(last["stn_median"]),
                "stn_std":           float(last["stn_std"]),
                "stn_max":           float(last["stn_max"]),
                "stn_rank_pct":      float(last["stn_rank_pct"]),
                "stn_hotspot_rate":  float(last["stn_hotspot_rate"]),
                "crime_per_1k_riders": float(last["crime_per_1k_riders"]) if pd.notna(last.get("crime_per_1k_riders")) else 0.0,
                "score_per_1k_riders": float(last["score_per_1k_riders"]) if pd.notna(last.get("score_per_1k_riders")) else 0.0,
                "month":    int(dt.month),
                "year":     int(dt.year),
                "bor_enc":  int(last["bor_enc"]),
            }

            x    = pd.DataFrame([feat_row])[feats]
            p    = float(m2.predict_proba(x)[:, 1][0])
            pred = int(p >= threshold)

            rows.append({
                "station_name":           stn,
                "borough":                last.get("borough", "UNKNOWN"),
                "month":                  dt.strftime("%Y-%m-%d"),
                "predicted_hotspot_prob": round(p, 6),
                "predicted_hotspot_label": pred,
                "confidence_bucket":      confidence_bucket(p),
                "scenario_mode":          scenario,
            })

            hot_hist   = (hot_hist   + [float(pred)])[-12:]
            cnt_hist   = (cnt_hist   + [cnt_next])[-6:]
            score_hist = (score_hist + [score_next])[-6:]
            rank_hist  = (rank_hist  + [rank_next])[-6:]

    out = pd.DataFrame(rows)
    out.to_csv(OUT2, index=False)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast 2027-2029 risk outputs.")
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIO_MULTIPLIERS.keys()),
        default="baseline",
        help="Forecast scenario (baseline / conservative / stress).",
    )
    args = parser.parse_args()

    print("Forecast run for 2027-2029")
    print(f"Model backend: {'XGBoost' if HAS_XGBOOST else 'HistGradientBoosting fallback'}")
    print(f"Scenario mode: {args.scenario}")

    print("\nRunning Model 1 forecast (Elevator & Escalator)...")
    f1 = forecast_model1(args.scenario)

    print("Running Model 2 forecast (Crime Hotspot)...")
    f2 = forecast_model2(args.scenario)

    ctx     = create_run_context("forecast")
    out1_run = copy_to_run_dir(ctx, OUT1)
    out2_run = copy_to_run_dir(ctx, OUT2)

    write_run_metadata(ctx, {
        "status":        "success",
        "scenario_mode": args.scenario,
        "model_backend": "XGBoost" if HAS_XGBOOST else "HistGradientBoosting fallback",
        "row_counts":    {"model1_rows": int(len(f1)), "model2_rows": int(len(f2))},
        "positive_predictions": {
            "model1": int(f1["predicted_service_label"].sum()),
            "model2": int(f2["predicted_hotspot_label"].sum()),
        },
        "outputs": {"model1_csv": out1_run, "model2_csv": out2_run},
    })
    update_latest_pointer(ctx)

    print("\nModel 1 summary (Elevator & Escalator servicing need)")
    for eq_type in ["Elevator", "Escalator"]:
        subset = f1[f1["equipment_type"] == eq_type]
        urgent  = (subset["severity"] == "URGENT").sum()
        monitor = (subset["severity"] == "MONITOR").sum()
        print(f"  [{eq_type}] rows={len(subset):,} | positives={subset['predicted_service_label'].sum():,}"
              f" | 🔴 URGENT={urgent:,}  🟡 MONITOR={monitor:,}")

    print("\nModel 2 summary (Crime hotspot)")
    print(f"  Forecast rows: {len(f2):,}")
    print(f"  Predicted hotspot positives: {int(f2['predicted_hotspot_label'].sum()):,}")
    print(f"  Mean hotspot probability: {f2['predicted_hotspot_prob'].mean():.4f}")

    print(f"\nSaved:")
    print(f"  {OUT1}")
    print(f"  {OUT2}")
    print(f"  Versioned artifacts: {ctx.run_dir}")


if __name__ == "__main__":
    main()
