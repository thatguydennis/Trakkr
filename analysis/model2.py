"""
model2.py
Station Crime Hotspot Classifier.

Target: is this station in the top 5 by crime count within its borough this month?
Optimizes for >=95% recall so police/transit departments proactively cover at-risk stations.
"""

import os
import warnings

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score

from artifacts import create_run_context, update_latest_pointer, write_json, write_run_metadata
from data_contracts import CRIME_CONTRACT, require_columns, validate_dataframe_contract
from features import (
    CRIME_FEATS,
    HAS_XGBOOST,
    build_crime_features,
    make_crime_model,
    pick_recall_threshold,
)

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "data", "clean")

TRAIN_CUTOFF  = 2024
VAL_YEAR      = 2024
TEST_START    = 2025
TARGET_RECALL = 0.95
# XGBoost probability calibration shifts between val and test years; use a
# stricter val target so the deployed threshold has recall headroom on 2025 data.
THRESH_SELECT_RECALL = 0.99


def main() -> None:
    print("Running Model 2: Station Crime Hotspot Classifier (top 5 per borough)")
    crime = pd.read_csv(os.path.join(CLEAN, "crime_clean.csv"), parse_dates=["date"])
    validate_dataframe_contract(crime, CRIME_CONTRACT)
    require_columns(
        crime,
        ["date", "year", "month", "station_name", "boro_nm"],
        "crime_clean.csv",
    )

    cm_ml, feats, _le_bor = build_crime_features(crime, unit_stats_cutoff_year=TRAIN_CUTOFF)
    cm_ml = cm_ml.dropna(subset=feats + ["is_hotspot"]).copy()

    print(f"  Dataset: {len(cm_ml):,} rows | hotspot rate: {cm_ml['is_hotspot'].mean()*100:.1f}%")
    print(f"  Hotspots per borough-month: top 5")

    x_tr_thresh = cm_ml.loc[cm_ml["year"] < VAL_YEAR, feats]
    y_tr_thresh = cm_ml.loc[cm_ml["year"] < VAL_YEAR, "is_hotspot"]
    x_val = cm_ml.loc[cm_ml["year"] == VAL_YEAR, feats]
    y_val = cm_ml.loc[cm_ml["year"] == VAL_YEAR, "is_hotspot"]

    x_tr = cm_ml.loc[cm_ml["year"] <= TRAIN_CUTOFF, feats]
    y_tr = cm_ml.loc[cm_ml["year"] <= TRAIN_CUTOFF, "is_hotspot"]
    x_te = cm_ml.loc[cm_ml["year"] >= TEST_START, feats]
    y_te = cm_ml.loc[cm_ml["year"] >= TEST_START, "is_hotspot"]

    pos_w_thresh = (y_tr_thresh == 0).sum() / max((y_tr_thresh == 1).sum(), 1)
    m_thresh = make_crime_model(pos_w_thresh, n_estimators=400)
    m_thresh.fit(x_tr_thresh, y_tr_thresh)
    best_t = pick_recall_threshold(m_thresh, x_val, y_val, target_recall=THRESH_SELECT_RECALL)

    pos_weight = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    model = make_crime_model(pos_weight)
    model.fit(x_tr, y_tr)

    proba = model.predict_proba(x_te)[:, 1]
    pred = (proba >= best_t).astype(int)

    cv = cross_val_score(
        make_crime_model(pos_weight, n_estimators=400),
        x_tr, y_tr,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        scoring="recall",
    )

    acc  = accuracy_score(y_te, pred) * 100
    auc  = roc_auc_score(y_te, proba)
    prec = precision_score(y_te, pred, zero_division=0) * 100
    rec  = recall_score(y_te, pred, zero_division=0) * 100
    f1   = f1_score(y_te, pred, zero_division=0) * 100

    print(f"Model backend: {'XGBoost' if HAS_XGBOOST else 'HistGradientBoosting'}")
    print(f"Train rows: {len(x_tr):,} | Val rows: {len(x_val):,} | Test rows: {len(x_te):,}")
    print(f"Hotspot rate (test): {y_te.mean() * 100:.2f}%")
    print(f"Threshold (≥{int(TARGET_RECALL*100)}% recall on val): {best_t:.2f}")
    print(f"Accuracy:  {acc:.2f}%")
    print(f"AUC:       {auc:.4f}")
    print(f"Precision: {prec:.1f}%")
    print(f"Recall:    {rec:.1f}%  ← primary metric")
    print(f"F1:        {f1:.1f}%")
    print(f"CV Recall (train): {cv.mean()*100:.2f}% ± {cv.std()*100:.2f}%")

    ctx = create_run_context("model2")
    joblib.dump(model, os.path.join(ctx.run_dir, "model2.joblib"))
    write_json(os.path.join(ctx.run_dir, "threshold_model2.json"), {"threshold": round(float(best_t), 4)})

    summary_path = os.path.join(ctx.run_dir, "model2_summary.json")
    metrics = {
        "accuracy_pct":   round(acc,  2),
        "auc":            round(auc,  4),
        "precision_pct":  round(prec, 1),
        "recall_pct":     round(rec,  1),
        "f1_pct":         round(f1,   1),
        "threshold":      round(float(best_t), 2),
        "cv_recall_mean": round(float(cv.mean() * 100), 2),
        "cv_recall_std":  round(float(cv.std()  * 100), 2),
        "train_rows":     int(len(x_tr)),
        "val_rows":       int(len(x_val)),
        "test_rows":      int(len(x_te)),
    }
    pd.DataFrame([metrics]).to_json(summary_path, orient="records", indent=2)

    write_run_metadata(ctx, {
        "status": "success",
        "target": "is_hotspot_top5_per_borough",
        "target_recall": TARGET_RECALL,
        "dataset": "data/clean/crime_clean.csv",
        "model_backend": "XGBoost" if HAS_XGBOOST else "HistGradientBoosting",
        "splits": {"train_cutoff": TRAIN_CUTOFF, "val_year": VAL_YEAR, "test_start": TEST_START},
        "metrics": metrics,
    })
    update_latest_pointer(ctx)
    print(f"Versioned artifacts written to: {ctx.run_dir}")


if __name__ == "__main__":
    main()
