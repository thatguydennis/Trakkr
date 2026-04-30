"""
drift_monitor.py
Model drift detection for Model 1 (Elevator) and Model 2 (Crime Hotspot).

Loads the latest saved models, runs them against the most recent N months of
clean data, compares recall and AUC to the baseline recorded at training time,
and prints a clear pass/warn/fail report.

Usage:
    python drift_monitor.py              # checks last 3 months by default
    python drift_monitor.py --months 6  # check last 6 months
"""

from __future__ import annotations

import argparse
import json
import os
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import recall_score, roc_auc_score

from features import (
    CRIME_FEATS,
    ELEVATOR_FEATS,
    build_crime_features,
    build_elevator_features,
    classify_severity,
)

warnings.filterwarnings("ignore")

BASE  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "data", "clean")
LATEST_ROOT = os.path.join(BASE, "data", "artifacts", "latest")

# Thresholds that trigger a warning or failure alert
WARN_RECALL_DROP  = 3.0   # warn if recall falls >3 pct points below baseline
FAIL_RECALL_DROP  = 7.0   # fail if recall falls >7 pct points below baseline
WARN_AUC_DROP     = 0.03
FAIL_AUC_DROP     = 0.07


# ─────────────────────────────────────────────────────────────────────────────
# Artifact loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_latest_pointer(pipeline: str) -> dict:
    path = os.path.join(LATEST_ROOT, f"{pipeline}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No latest pointer for '{pipeline}'. Run the model first.")
    with open(path) as f:
        return json.load(f)


def _load_model_and_threshold(run_dir: str, model_file: str, threshold_file: str):
    model = joblib.load(os.path.join(run_dir, model_file))
    with open(os.path.join(run_dir, threshold_file)) as f:
        threshold = json.load(f)["threshold"]
    return model, threshold


def _load_baseline_metrics(run_dir: str, summary_file: str) -> list[dict]:
    path = os.path.join(run_dir, summary_file)
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


# ─────────────────────────────────────────────────────────────────────────────
# Status helpers
# ─────────────────────────────────────────────────────────────────────────────

def _status(drop: float, warn_t: float, fail_t: float) -> str:
    if drop >= fail_t:
        return "FAIL"
    if drop >= warn_t:
        return "WARN"
    return "OK"


def _icon(status: str) -> str:
    return {"OK": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[status]


def _print_metric_row(name: str, baseline: float, current: float, drop: float, status: str) -> None:
    print(f"    {_icon(status)} {name:<18} baseline={baseline:.2f}  current={current:.2f}  drop={drop:+.2f}  [{status}]")


# ─────────────────────────────────────────────────────────────────────────────
# Model 1 drift check
# ─────────────────────────────────────────────────────────────────────────────

def check_model1(recent_months: int) -> bool:
    print("\n── Model 1: Elevator & Escalator Servicing Need Predictor ──────────────")
    ptr = _load_latest_pointer("model1")
    run_dir = ptr["latest_run_dir"]

    elev = pd.read_csv(os.path.join(CLEAN, "elevator_clean.csv"), parse_dates=["month"])
    max_year  = elev["month"].dt.year.max()
    max_month = elev.loc[elev["month"].dt.year == max_year, "month"].dt.month.max()
    # Subtract (recent_months - 1) so the cutoff falls at the START of the oldest month
    # we want to include, giving exactly recent_months months in [cutoff_dt, max_month].
    cutoff_dt = pd.Timestamp(year=max_year, month=max_month, day=1) - pd.DateOffset(months=recent_months - 1)

    elev_ml, feats, _, _ = build_elevator_features(elev, unit_stats_cutoff_year=max_year - 1)
    elev_ml = elev_ml.dropna(subset=["needs_service_next"]).copy()
    recent = elev_ml[elev_ml["month"] >= cutoff_dt]

    if len(recent) == 0:
        print("  No recent data found — skipping Model 1 check.")
        return True

    print(f"  Checking last {recent_months} months: {cutoff_dt.date()} → present  ({len(recent):,} rows)")

    baselines = _load_baseline_metrics(run_dir, "model1_summary.json")
    all_ok = True

    for row in baselines:
        eq_type = row.get("equipment_type", "All")
        slug    = eq_type.lower()

        model_file     = f"model1_{slug}.joblib"
        threshold_file = f"threshold_model1_{slug}.json"
        if not os.path.exists(os.path.join(run_dir, model_file)):
            # Legacy single-model artifact
            model_file, threshold_file = "model1.joblib", "threshold_model1.json"

        try:
            model, threshold = _load_model_and_threshold(run_dir, model_file, threshold_file)
        except FileNotFoundError:
            print(f"  [{eq_type}] artifact not found — skipping.")
            continue

        subset = recent[recent["equipment_type"] == eq_type] if eq_type != "All" else recent
        if len(subset) == 0:
            print(f"  [{eq_type}] no recent rows — skipping.")
            continue

        x = subset[feats]
        y = subset["needs_service_next"]
        proba = model.predict_proba(x)[:, 1]
        pred  = (proba >= threshold).astype(int)

        cur_recall = recall_score(y, pred, zero_division=0) * 100
        cur_auc    = roc_auc_score(y, proba)

        base_recall = row["recall_pct"]
        base_auc    = row["auc"]
        recall_drop = base_recall - cur_recall
        auc_drop    = base_auc - cur_auc

        r_status = _status(recall_drop, WARN_RECALL_DROP, FAIL_RECALL_DROP)
        a_status = _status(auc_drop, WARN_AUC_DROP, FAIL_AUC_DROP)

        entrap_hist = subset["unit_entrap_rate"].values
        severity    = classify_severity(proba, threshold, entrap_hist)
        n_urgent    = int((severity == "URGENT").sum())
        n_monitor   = int((severity == "MONITOR").sum())

        print(f"\n  [{eq_type}]  rows={len(subset):,}  threshold={threshold:.2f}")
        _print_metric_row("Recall",  base_recall,       cur_recall,       recall_drop, r_status)
        _print_metric_row("AUC",     base_auc * 100,    cur_auc * 100,    auc_drop * 100, a_status)
        print(f"    🔴 URGENT: {n_urgent}   🟡 MONITOR: {n_monitor}   🟢 LOW: {len(subset)-n_urgent-n_monitor}")

        if r_status == "FAIL" or a_status == "FAIL":
            all_ok = False
            print(f"    ⚠️  DRIFT DETECTED for {eq_type} — consider retraining.")

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Model 2 drift check
# ─────────────────────────────────────────────────────────────────────────────

def check_model2(recent_months: int) -> bool:
    print("\n── Model 2: Station Crime Hotspot Classifier ───────────────────────────")
    ptr = _load_latest_pointer("model2")
    run_dir = ptr["latest_run_dir"]

    crime = pd.read_csv(os.path.join(CLEAN, "crime_clean.csv"), parse_dates=["date"])
    max_year  = crime["year"].max()
    max_month = crime.loc[crime["year"] == max_year, "month"].max()

    # Use DateOffset (same as Model 1) to avoid month-13 edge-cases in manual arithmetic.
    # Subtracting (recent_months - 1) places the cutoff at the START of the oldest month
    # we want to include, giving exactly recent_months months in [cutoff_dt, max_month].
    max_dt    = pd.Timestamp(year=int(max_year), month=int(max_month), day=1)
    cutoff_dt = max_dt - pd.DateOffset(months=recent_months - 1)
    cutoff_year  = cutoff_dt.year
    cutoff_month = cutoff_dt.month

    cm, feats, _ = build_crime_features(crime, unit_stats_cutoff_year=max_year - 1)
    cm = cm.dropna(subset=feats + ["is_hotspot"]).copy()

    recent_mask = (cm["year"] > cutoff_year) | (
        (cm["year"] == cutoff_year) & (cm["month"] >= cutoff_month)
    )
    recent = cm[recent_mask]

    if len(recent) == 0:
        print("  No recent crime data found — skipping Model 2 check.")
        return True

    print(f"  Checking last {recent_months} months: ({len(recent):,} rows, hotspot rate {recent['is_hotspot'].mean()*100:.1f}%)")

    model, threshold = _load_model_and_threshold(
        run_dir, "model2.joblib", "threshold_model2.json"
    )
    baselines = _load_baseline_metrics(run_dir, "model2_summary.json")
    row = baselines[0]

    x = recent[feats]
    y = recent["is_hotspot"]
    proba = model.predict_proba(x)[:, 1]
    pred  = (proba >= threshold).astype(int)

    cur_recall = recall_score(y, pred, zero_division=0) * 100
    cur_auc    = roc_auc_score(y, proba)

    base_recall = row["recall_pct"]
    base_auc    = row["auc"]
    recall_drop = base_recall - cur_recall
    auc_drop    = base_auc - cur_auc

    r_status = _status(recall_drop, WARN_RECALL_DROP, FAIL_RECALL_DROP)
    a_status = _status(auc_drop, WARN_AUC_DROP, FAIL_AUC_DROP)

    print(f"  threshold={threshold:.2f}")
    _print_metric_row("Recall", base_recall,    cur_recall,    recall_drop, r_status)
    _print_metric_row("AUC",    base_auc * 100, cur_auc * 100, auc_drop * 100, a_status)

    if r_status == "FAIL" or a_status == "FAIL":
        print("    ⚠️  DRIFT DETECTED — consider retraining Model 2.")
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Check for model drift against recent data.")
    parser.add_argument("--months", type=int, default=3, help="Number of recent months to evaluate (default: 3)")
    args = parser.parse_args()

    print(f"Drift Monitor — evaluating last {args.months} months of data")
    print("=" * 70)

    ok1 = check_model1(args.months)
    ok2 = check_model2(args.months)

    print("\n" + "=" * 70)
    if ok1 and ok2:
        print("✅  All models within acceptable drift bounds. No action needed.")
    else:
        print("❌  One or more models show significant drift. Retrain recommended.")
        print("    Run:  python clean_data.py && python model1.py && python model2.py")


if __name__ == "__main__":
    main()
