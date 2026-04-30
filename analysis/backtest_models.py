"""
Rolling walk-forward backtest for Model 1 (Elevator/Escalator) and Model 2 (Crime Hotspot).

For each training cutoff year, trains fresh models on data up to that year and
evaluates on the next year. Reports recall (primary), AUC, precision, and F1
to show model stability over time.
"""

from __future__ import annotations

import os
import warnings
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

from artifacts import create_run_context, update_latest_pointer, write_run_metadata
from data_contracts import CRIME_CONTRACT, ELEVATOR_CONTRACT, require_columns, validate_dataframe_contract
from features import (
    CRIME_FEATS,
    ELEVATOR_FEATS,
    HAS_XGBOOST,
    attach_crime_station_stats,
    attach_elevator_unit_stats,
    build_crime_base_features,
    build_elevator_base_features,
    cold_start_backfill,
    make_crime_model,
    make_elevator_model,
    pick_recall_threshold,
)

warnings.filterwarnings("ignore")

BASE  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "data", "clean")

TARGET_RECALL = 0.95
MIN_TRAIN_ROWS = 1000
MIN_VAL_ROWS   = 50
MIN_TEST_ROWS  = 100


def evaluate_binary(y_true: pd.Series, proba: np.ndarray, threshold: float) -> Dict[str, float]:
    pred = (proba >= threshold).astype(int)
    return {
        "threshold":      round(threshold, 3),
        "accuracy_pct":   round(float(accuracy_score(y_true, pred) * 100), 2),
        "auc":            round(float(roc_auc_score(y_true, proba)), 4),
        "precision_pct":  round(float(precision_score(y_true, pred, zero_division=0) * 100), 1),
        "recall_pct":     round(float(recall_score(y_true, pred, zero_division=0) * 100), 1),
        "f1_pct":         round(float(f1_score(y_true, pred, zero_division=0) * 100), 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Model 1 backtest — separate folds per equipment type
# ─────────────────────────────────────────────────────────────────────────────

def backtest_model1() -> pd.DataFrame:
    elev = pd.read_csv(os.path.join(CLEAN, "elevator_clean.csv"), parse_dates=["month"])
    validate_dataframe_contract(elev, ELEVATOR_CONTRACT)
    require_columns(
        elev,
        ["month", "equipment_code", "equipment_type", "borough",
         "am_peak_availability", "unscheduled_outages", "entrapments",
         "time_since_major_improvement"],
        "elevator_clean.csv",
    )

    elev_base, _le_eq, _le_bor = build_elevator_base_features(elev)
    years = sorted(int(y) for y in elev_base["year"].unique())
    results: List[Dict] = []

    for train_end in years:
        test_year = train_end + 1

        # Per-fold unit stats from training window only (no leakage)
        elev_fold = attach_elevator_unit_stats(elev_base.copy(), unit_stats_cutoff_year=train_end)
        elev_fold = cold_start_backfill(elev_fold, ELEVATOR_FEATS, train_end)
        elev_ml   = elev_fold.dropna(subset=["needs_service_next"]).copy()

        for eq_type in ["Elevator", "Escalator"]:
            subset = elev_ml[elev_ml["equipment_type"] == eq_type]

            tr       = subset[subset["year"] <= train_end]
            tr_thresh = subset[subset["year"] < train_end]
            val      = subset[subset["year"] == train_end]
            te       = subset[subset["year"] == test_year]

            if len(tr) < MIN_TRAIN_ROWS or len(val) < MIN_VAL_ROWS or len(te) < MIN_TEST_ROWS:
                continue
            if len(tr_thresh) < 500:
                continue

            pos_w_thresh = (tr_thresh["needs_service_next"] == 0).sum() / max(
                (tr_thresh["needs_service_next"] == 1).sum(), 1
            )
            m_thresh = make_elevator_model(pos_w_thresh, n_estimators=200)
            m_thresh.fit(tr_thresh[ELEVATOR_FEATS], tr_thresh["needs_service_next"])
            best_t = pick_recall_threshold(
                m_thresh, val[ELEVATOR_FEATS], val["needs_service_next"],
                target_recall=TARGET_RECALL,
            )

            x_tr, y_tr = tr[ELEVATOR_FEATS], tr["needs_service_next"]
            x_te, y_te = te[ELEVATOR_FEATS], te["needs_service_next"]
            pos_weight  = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
            model = make_elevator_model(pos_weight, n_estimators=400)
            model.fit(x_tr, y_tr)
            proba = model.predict_proba(x_te)[:, 1]

            metrics = evaluate_binary(y_te, proba, best_t)
            results.append({
                "model":             f"model1_{eq_type.lower()}",
                "equipment_type":    eq_type,
                "train_through_year": train_end,
                "test_year":         test_year,
                **metrics,
            })

    return pd.DataFrame(results)


# ─────────────────────────────────────────────────────────────────────────────
# Model 2 backtest
# ─────────────────────────────────────────────────────────────────────────────

def backtest_model2() -> pd.DataFrame:
    crime = pd.read_csv(os.path.join(CLEAN, "crime_clean.csv"), parse_dates=["date"])
    validate_dataframe_contract(crime, CRIME_CONTRACT)
    require_columns(crime, ["date", "year", "month", "station_name", "boro_nm"], "crime_clean.csv")

    cm_base, _le_bor = build_crime_base_features(crime)
    years = sorted(int(y) for y in cm_base["year"].unique())
    results: List[Dict] = []

    for train_end in years:
        test_year = train_end + 1

        cm_fold = attach_crime_station_stats(cm_base.copy(), unit_stats_cutoff_year=train_end)
        cm_ml   = cm_fold.dropna(subset=CRIME_FEATS + ["is_hotspot"]).copy()

        tr        = cm_ml[cm_ml["year"] <= train_end]
        tr_thresh = cm_ml[cm_ml["year"] < train_end]
        val       = cm_ml[cm_ml["year"] == train_end]
        te        = cm_ml[cm_ml["year"] == test_year]

        if len(tr) < MIN_TRAIN_ROWS or len(val) < MIN_VAL_ROWS or len(te) < MIN_TEST_ROWS:
            continue
        if len(tr_thresh) < 500:
            continue

        pos_w_thresh = (tr_thresh["is_hotspot"] == 0).sum() / max(
            (tr_thresh["is_hotspot"] == 1).sum(), 1
        )
        m_thresh = make_crime_model(pos_w_thresh, n_estimators=200)
        m_thresh.fit(tr_thresh[CRIME_FEATS], tr_thresh["is_hotspot"])
        best_t = pick_recall_threshold(
            m_thresh, val[CRIME_FEATS], val["is_hotspot"],
            target_recall=TARGET_RECALL,
        )

        x_tr, y_tr = tr[CRIME_FEATS], tr["is_hotspot"]
        x_te, y_te = te[CRIME_FEATS], te["is_hotspot"]
        pos_weight  = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
        model = make_crime_model(pos_weight, n_estimators=400)
        model.fit(x_tr, y_tr)
        proba = model.predict_proba(x_te)[:, 1]

        metrics = evaluate_binary(y_te, proba, best_t)
        results.append({
            "model":             "model2",
            "train_through_year": train_end,
            "test_year":         test_year,
            **metrics,
        })

    return pd.DataFrame(results)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Running walk-forward backtest | backend: {'XGBoost' if HAS_XGBOOST else 'HistGradientBoosting'}")

    print("  Backtesting Model 1 (Elevator & Escalator)...")
    m1 = backtest_model1()
    print("  Backtesting Model 2 (Crime Hotspot)...")
    m2 = backtest_model2()

    out = pd.concat([m1, m2], ignore_index=True)

    ctx = create_run_context("backtest")
    csv_out = os.path.join(ctx.run_dir, "backtest_results.csv")
    out.to_csv(csv_out, index=False)

    summary = (
        out.groupby("model")[["auc", "recall_pct", "precision_pct", "f1_pct"]]
        .mean()
        .round(3)
        .to_dict(orient="index")
    )
    write_run_metadata(ctx, {
        "status":        "success",
        "model_backend": "XGBoost" if HAS_XGBOOST else "HistGradientBoosting",
        "results_csv":   csv_out,
        "rows":          int(len(out)),
        "summary_means": summary,
    })
    update_latest_pointer(ctx)

    print(f"\nBacktest results ({len(out)} folds):")
    print(out.to_string(index=False))
    print(f"\nMeans by model:")
    for model_name, stats in summary.items():
        print(f"  {model_name}: recall={stats['recall_pct']:.1f}%  AUC={stats['auc']:.4f}  F1={stats['f1_pct']:.1f}%")
    print(f"\nVersioned artifacts written to: {ctx.run_dir}")


if __name__ == "__main__":
    main()
