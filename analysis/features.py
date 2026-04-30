"""
Shared feature engineering and model factories for Model 1 (Elevator) and Model 2 (Crime).
Imported by model1.py, model2.py, predict_2027_2029.py, and backtest_models.py.

Model 1 target: needs_service_next — will this unit have an unscheduled outage OR entrapment
                in the following month? Predicts servicing need 30 days out.

Model 2 target: is_hotspot — is this station in the top 5 by crime count within its borough
                for that month?
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.preprocessing import LabelEncoder

try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except Exception:
    HAS_XGBOOST = False


# ─────────────────────────────────────────────────────────────────────────────
# Feature lists
# ─────────────────────────────────────────────────────────────────────────────

ELEVATOR_FEATS: List[str] = [
    # Availability lags
    "avail_lag1", "avail_lag2", "avail_lag3", "avail_lag6",
    # Unscheduled outage lags
    "unsch_lag1", "unsch_lag2", "unsch_lag3", "unsch_lag6",
    # Entrapment lags
    "trap_lag1", "trap_lag2", "trap_lag3",
    # Service event lags (was service needed in past months)
    "svc_lag1", "svc_lag2", "svc_lag3", "svc_lag6",
    # Scheduled outage lags
    "sched_lag1", "sched_lag3",
    # Rolling features
    "avail_roll3", "avail_roll6",
    "unsch_roll3", "unsch_roll6",
    "svc_roll3", "svc_roll6",
    # Unit-level historical stats (recomputed per fold from training window)
    "unit_svc_rate", "unit_mean_outages", "unit_entrap_rate", "unit_mean_avail",
    # Station-level stats
    "stn_svc_rate", "stn_mean_outages",
    # Metadata
    "time_since_major_improvement",
    "eq_enc",
    "bor_enc",
    "month_num",
    "year",
]

CRIME_FEATS: List[str] = [
    # Raw count lags
    "cnt_lag1", "cnt_lag2", "cnt_lag3", "cnt_lag6",
    # Hotspot and rank lags
    "hotspot_lag1", "hotspot_lag2", "hotspot_lag3", "hotspot_lag6",
    "rank_lag1", "rank_lag2", "rank_lag3",
    # Raw count rolling
    "roll_mean3", "roll_mean6",
    "roll_hot3", "pct_hot_12m",
    # Weighted crime score lags (Felony=3, Misdemeanor=2, Violation=1)
    "score_lag1", "score_lag2", "score_lag3", "score_lag6",
    # Weighted score rolling
    "score_roll3", "score_roll6",
    # Velocity / trend (3-month change — rising stations are more likely to hit top 5)
    "cnt_velocity_3m", "cnt_pct_chg_3m", "score_velocity_3m",
    # Station-level historical stats
    "stn_mean", "stn_median", "stn_std", "stn_max",
    "stn_rank_pct", "stn_hotspot_rate",
    # Ridership normalization (crimes per 1,000 monthly riders)
    "crime_per_1k_riders", "score_per_1k_riders",
    # Time and geography
    "month", "year", "bor_enc",
]


# ─────────────────────────────────────────────────────────────────────────────
# Elevator feature helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_elevator_base_features(
    elev: pd.DataFrame,
) -> Tuple[pd.DataFrame, LabelEncoder, LabelEncoder]:
    """Sort, compute service target, lag/rolling features.

    Target: needs_service_next = did this unit have unscheduled_outages > 0
            OR entrapments > 0 in the FOLLOWING month (predicts 30-day need).

    Does NOT add unit/station-level stats — call attach_elevator_unit_stats() for those.
    Returns (DataFrame, le_equipment_type, le_borough).
    """
    elev_s = elev.sort_values(["equipment_code", "month"]).copy()
    elev_s["year"] = elev_s["month"].dt.year
    elev_s["month_num"] = elev_s["month"].dt.month

    elev_s["unscheduled_outages"] = pd.to_numeric(elev_s["unscheduled_outages"], errors="coerce").fillna(0)
    elev_s["entrapments"] = pd.to_numeric(elev_s["entrapments"], errors="coerce").fillna(0)
    elev_s["scheduled_outages"] = pd.to_numeric(elev_s["scheduled_outages"], errors="coerce").fillna(0)
    elev_s["am_peak_availability"] = pd.to_numeric(elev_s["am_peak_availability"], errors="coerce")
    elev_s["time_since_major_improvement"] = pd.to_numeric(
        elev_s["time_since_major_improvement"], errors="coerce"
    ).fillna(0)

    # Current-month service event (input signal)
    elev_s["needs_service"] = (
        (elev_s["unscheduled_outages"] > 0) | (elev_s["entrapments"] > 0)
    ).astype(int)

    # Target: next month's service event (shift backward by 1)
    elev_s["needs_service_next"] = (
        elev_s.groupby("equipment_code")["needs_service"].shift(-1)
    )

    # Lag features (from history — shift forward so no leakage)
    for lag in [1, 2, 3, 6]:
        elev_s[f"avail_lag{lag}"] = elev_s.groupby("equipment_code")["am_peak_availability"].shift(lag)
        elev_s[f"unsch_lag{lag}"] = elev_s.groupby("equipment_code")["unscheduled_outages"].shift(lag)
        elev_s[f"svc_lag{lag}"] = elev_s.groupby("equipment_code")["needs_service"].shift(lag)

    for lag in [1, 2, 3]:
        elev_s[f"trap_lag{lag}"] = elev_s.groupby("equipment_code")["entrapments"].shift(lag)

    for lag in [1, 3]:
        elev_s[f"sched_lag{lag}"] = elev_s.groupby("equipment_code")["scheduled_outages"].shift(lag)

    # Rolling features (shift by 1 to avoid leaking current month)
    for window, suffix in [(3, "3"), (6, "6")]:
        elev_s[f"avail_roll{suffix}"] = elev_s.groupby("equipment_code")["am_peak_availability"].transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).mean()
        )
        elev_s[f"unsch_roll{suffix}"] = elev_s.groupby("equipment_code")["unscheduled_outages"].transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).mean()
        )
        elev_s[f"svc_roll{suffix}"] = elev_s.groupby("equipment_code")["needs_service"].transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).mean()
        )

    le_eq = LabelEncoder()
    le_bor = LabelEncoder()
    elev_s["eq_enc"] = le_eq.fit_transform(elev_s["equipment_type"].fillna("Unknown"))
    elev_s["bor_enc"] = le_bor.fit_transform(elev_s["borough"].fillna("Unknown"))

    return elev_s, le_eq, le_bor


def attach_elevator_unit_stats(elev_s: pd.DataFrame, unit_stats_cutoff_year: int) -> pd.DataFrame:
    """Attach per-unit and per-station historical stats from years <= cutoff."""
    stat_cols = ["unit_svc_rate", "unit_mean_outages", "unit_entrap_rate", "unit_mean_avail",
                 "stn_svc_rate", "stn_mean_outages"]
    elev_s = elev_s.drop(columns=[c for c in stat_cols if c in elev_s.columns])

    train = elev_s[elev_s["year"] <= unit_stats_cutoff_year]

    unit_stats = train.groupby("equipment_code").agg(
        unit_svc_rate=("needs_service", "mean"),
        unit_mean_outages=("unscheduled_outages", "mean"),
        unit_entrap_rate=("entrapments", lambda x: (x > 0).mean()),
        unit_mean_avail=("am_peak_availability", "mean"),
    )
    elev_s = elev_s.join(unit_stats, on="equipment_code")

    # Station-level stats (aggregated across all equipment at a station)
    if "station_name" in elev_s.columns:
        stn_stats = train.groupby("station_name").agg(
            stn_svc_rate=("needs_service", "mean"),
            stn_mean_outages=("unscheduled_outages", "mean"),
        )
        elev_s = elev_s.join(stn_stats, on="station_name")
    else:
        elev_s["stn_svc_rate"] = np.nan
        elev_s["stn_mean_outages"] = np.nan

    return elev_s


def cold_start_backfill(elev_s: pd.DataFrame, feats: List[str], cutoff_year: int) -> pd.DataFrame:
    """Fill NaN lag/rolling features for new equipment with equipment_type+borough averages.

    New units have no history so their lag columns are NaN. Instead of dropping
    those rows entirely, substitute the mean value for units of the same type
    and borough computed from the training window. This lets new equipment get
    a reasonable prior rather than being silently excluded.
    """
    lag_feats = [f for f in feats if f not in ("eq_enc", "bor_enc", "month_num", "year",
                                                 "unit_svc_rate", "unit_mean_outages",
                                                 "unit_entrap_rate", "unit_mean_avail",
                                                 "stn_svc_rate", "stn_mean_outages",
                                                 "time_since_major_improvement")]
    train = elev_s[elev_s["year"] <= cutoff_year]
    group_means = train.groupby(["equipment_type", "borough"])[lag_feats].mean()

    needs_fill = elev_s[lag_feats].isna().any(axis=1)
    if not needs_fill.any():
        return elev_s

    elev_s = elev_s.copy()
    fill_df = elev_s.join(group_means, on=["equipment_type", "borough"], rsuffix="_grp")
    for col in lag_feats:
        grp_col = f"{col}_grp"
        if grp_col in fill_df.columns:
            elev_s[col] = elev_s[col].fillna(fill_df[grp_col])

    return elev_s


def build_elevator_features(
    elev: pd.DataFrame,
    unit_stats_cutoff_year: int,
) -> Tuple[pd.DataFrame, List[str], LabelEncoder, LabelEncoder]:
    """Full elevator feature pipeline: lag/rolling + unit/station stats + cold-start backfill.

    Returns (DataFrame, feature_list, le_equipment, le_borough).
    """
    elev_s, le_eq, le_bor = build_elevator_base_features(elev)
    elev_s = attach_elevator_unit_stats(elev_s, unit_stats_cutoff_year)
    elev_s = cold_start_backfill(elev_s, ELEVATOR_FEATS, unit_stats_cutoff_year)
    return elev_s, ELEVATOR_FEATS, le_eq, le_bor


# ─────────────────────────────────────────────────────────────────────────────
# Crime feature helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_crime_base_features(
    crime: pd.DataFrame,
) -> Tuple[pd.DataFrame, LabelEncoder]:
    """Aggregate to station-month, compute top-5-per-borough hotspot label, lag/rolling features.

    Hotspot definition: station ranks in top 5 by crime count within its borough that month.
    Returns (DataFrame, le_borough).
    """
    crime_valid = crime[
        crime["station_name"].notna() &
        (crime["station_name"] != "NAN") &
        (crime["station_name"] != "(NULL)")
    ].copy()

    # Station → borough mapping (most common borough per station)
    stn_boro = (
        crime_valid.groupby("station_name")["boro_nm"]
        .agg(lambda x: x.mode()[0] if len(x) > 0 else "UNKNOWN")
    )

    # Weighted severity score: Felony=3, Misdemeanor=2, Violation=1
    _WEIGHTS = {"FELONY": 3, "MISDEMEANOR": 2, "VIOLATION": 1}
    crime_valid = crime_valid.copy()
    crime_valid["crime_weight"] = crime_valid["law_cat_cd"].map(_WEIGHTS).fillna(1)

    cm_agg = crime_valid.groupby(["station_name", "year", "month"]).agg(
        crime_count=("crime_weight", "count"),
        crime_score=("crime_weight", "sum"),
    ).reset_index()

    cm = cm_agg.copy()
    cm["month_dt"] = pd.to_datetime(cm[["year", "month"]].assign(day=1))
    cm = cm.sort_values(["station_name", "month_dt"]).reset_index(drop=True)
    cm["borough"] = cm["station_name"].map(stn_boro).fillna("UNKNOWN")

    # Rank within borough per month — top 5 by raw count = hotspot
    cm["rank_in_boro"] = cm.groupby(["borough", "year", "month"])["crime_count"].rank(
        method="first", ascending=False
    )
    cm["is_hotspot"] = (cm["rank_in_boro"] <= 5).astype(int)

    # Global rank pct (kept as a feature)
    cm["rank_pct"] = cm.groupby(["year", "month"])["crime_count"].rank(pct=True)

    # Lag features — raw count
    for lag in [1, 2, 3, 6]:
        cm[f"cnt_lag{lag}"] = cm.groupby("station_name")["crime_count"].shift(lag)
        cm[f"hotspot_lag{lag}"] = cm.groupby("station_name")["is_hotspot"].shift(lag)
        cm[f"rank_lag{lag}"] = cm.groupby("station_name")["rank_pct"].shift(lag)

    # Lag features — weighted score
    for lag in [1, 2, 3, 6]:
        cm[f"score_lag{lag}"] = cm.groupby("station_name")["crime_score"].shift(lag)

    # Rolling features — raw count
    cm["roll_mean3"] = cm.groupby("station_name")["crime_count"].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean()
    )
    cm["roll_mean6"] = cm.groupby("station_name")["crime_count"].transform(
        lambda x: x.shift(1).rolling(6, min_periods=1).mean()
    )
    cm["roll_hot3"] = cm.groupby("station_name")["is_hotspot"].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean()
    )
    cm["pct_hot_12m"] = cm.groupby("station_name")["is_hotspot"].transform(
        lambda x: x.shift(1).rolling(12, min_periods=3).mean()
    )

    # Rolling features — weighted score
    cm["score_roll3"] = cm.groupby("station_name")["crime_score"].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean()
    )
    cm["score_roll6"] = cm.groupby("station_name")["crime_score"].transform(
        lambda x: x.shift(1).rolling(6, min_periods=1).mean()
    )

    # Velocity / trend features — built from already-lagged values, no leakage
    # Absolute 3-month change in raw count (positive = rising crime)
    cm["cnt_velocity_3m"] = cm["cnt_lag1"] - cm["cnt_lag3"]
    # Relative 3-month change (+1 in denominator avoids division by zero)
    cm["cnt_pct_chg_3m"] = cm["cnt_velocity_3m"] / (cm["cnt_lag3"].abs() + 1)
    # Absolute 3-month change in weighted score
    cm["score_velocity_3m"] = cm["score_lag1"] - cm["score_lag3"]

    le_bor = LabelEncoder()
    cm["bor_enc"] = le_bor.fit_transform(cm["borough"])

    return cm, le_bor


def attach_crime_station_stats(cm: pd.DataFrame, unit_stats_cutoff_year: int) -> pd.DataFrame:
    """Attach per-station historical stats and ridership-normalized crime rates."""
    stat_cols = ["stn_mean", "stn_median", "stn_std", "stn_max", "stn_rank_pct", "stn_hotspot_rate",
                 "avg_monthly_ridership", "crime_per_1k_riders", "score_per_1k_riders"]
    cm = cm.drop(columns=[c for c in stat_cols if c in cm.columns])

    train_c = cm[cm["year"] <= unit_stats_cutoff_year]
    cm = cm.join(train_c.groupby("station_name")["crime_count"].mean().rename("stn_mean"), on="station_name")
    cm = cm.join(train_c.groupby("station_name")["crime_count"].median().rename("stn_median"), on="station_name")
    cm = cm.join(
        train_c.groupby("station_name")["crime_count"].std().fillna(0).rename("stn_std"), on="station_name"
    )
    cm = cm.join(train_c.groupby("station_name")["crime_count"].max().rename("stn_max"), on="station_name")
    cm = cm.join(
        train_c.groupby("station_name")["rank_pct"].mean().rename("stn_rank_pct"), on="station_name"
    )
    cm = cm.join(
        train_c.groupby("station_name")["is_hotspot"].mean().rename("stn_hotspot_rate"), on="station_name"
    )

    # Ridership normalization — load station ridership map if available
    import os
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rid_path = os.path.join(_BASE, "data", "clean", "station_ridership.csv")
    if os.path.exists(rid_path):
        rid = pd.read_csv(rid_path)
        rid["station_name"] = rid["station_name"].astype(str).str.strip().str.upper()
        rid = rid.set_index("station_name")["avg_monthly_ridership"]
        cm = cm.join(rid, on="station_name")

        # Fill stations missing ridership data with their borough average
        boro_avg = cm.groupby("borough")["avg_monthly_ridership"].transform(
            lambda x: x.fillna(x.median())
        )
        cm["avg_monthly_ridership"] = cm["avg_monthly_ridership"].fillna(boro_avg).fillna(50000)

        # Crimes per 1,000 monthly riders (avoids division by zero)
        cm["crime_per_1k_riders"] = cm["crime_count"] / (cm["avg_monthly_ridership"] / 1000).clip(lower=1)
        cm["score_per_1k_riders"] = cm["crime_score"]  / (cm["avg_monthly_ridership"] / 1000).clip(lower=1)
    else:
        cm["crime_per_1k_riders"] = np.nan
        cm["score_per_1k_riders"] = np.nan

    return cm


def build_crime_features(
    crime: pd.DataFrame,
    unit_stats_cutoff_year: int,
) -> Tuple[pd.DataFrame, List[str], LabelEncoder]:
    """Full crime feature pipeline: lag/rolling + station-level stats.

    Returns (DataFrame, feature_list, le_borough).
    """
    cm, le_bor = build_crime_base_features(crime)
    cm = attach_crime_station_stats(cm, unit_stats_cutoff_year)
    return cm, CRIME_FEATS, le_bor


# ─────────────────────────────────────────────────────────────────────────────
# Model factories
# ─────────────────────────────────────────────────────────────────────────────

def make_elevator_model(pos_weight: float, n_estimators: int = 600):
    if HAS_XGBOOST:
        return XGBClassifier(
            n_estimators=n_estimators,
            max_depth=6,
            learning_rate=0.02,
            subsample=0.80,
            colsample_bytree=0.80,
            min_child_weight=5,
            reg_alpha=0.3,
            reg_lambda=2.0,
            scale_pos_weight=pos_weight,
            random_state=42,
            tree_method="hist",
            verbosity=0,
            eval_metric="logloss",
        )
    # Fallback: HistGradientBoosting with balanced class weights handles imbalance
    return HistGradientBoostingClassifier(
        max_depth=6, learning_rate=0.02, max_iter=n_estimators,
        random_state=42, class_weight="balanced",
    )


def make_crime_model(pos_weight: float, n_estimators: int = 600):
    if HAS_XGBOOST:
        return XGBClassifier(
            n_estimators=n_estimators,
            max_depth=5,
            learning_rate=0.02,
            subsample=0.80,
            colsample_bytree=0.80,
            min_child_weight=3,
            reg_alpha=0.1,
            reg_lambda=1.5,
            scale_pos_weight=pos_weight,
            random_state=42,
            tree_method="hist",
            verbosity=0,
            eval_metric="logloss",
        )
    # Fallback: HistGradientBoosting with balanced class weights handles imbalance
    return HistGradientBoostingClassifier(
        max_depth=5, learning_rate=0.02, max_iter=n_estimators,
        random_state=42, class_weight="balanced",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Threshold selection
# ─────────────────────────────────────────────────────────────────────────────

def classify_severity(
    proba: np.ndarray,
    threshold: float,
    entrap_history: np.ndarray,
    urgent_proba: float = 0.70,
) -> np.ndarray:
    """Assign a severity tier to each Model 1 prediction.

    Returns an array of strings: 'URGENT', 'MONITOR', or 'LOW'.

    URGENT  — proba >= urgent_proba AND unit has prior entrapment history.
               Dispatch immediately; proven safety risk + high model confidence.
    MONITOR — proba >= threshold but not URGENT.
               Schedule for next maintenance window.
    LOW     — proba < threshold. No action needed this month.
    """
    severity = np.where(
        (proba >= urgent_proba) & (entrap_history > 0), "URGENT",
        np.where(proba >= threshold, "MONITOR", "LOW"),
    )
    return severity


def pick_threshold(model, x_val: pd.DataFrame, y_val: pd.Series) -> float:
    """F1-maximizing threshold on held-out val set. Falls back to 0.5."""
    proba = model.predict_proba(x_val)[:, 1]
    thresholds = np.arange(0.01, 0.99, 0.01)
    scores = [f1_score(y_val, (proba >= t).astype(int), zero_division=0) for t in thresholds]
    if max(scores) == 0.0:
        return 0.5
    return float(thresholds[np.argmax(scores)])


def pick_recall_threshold(
    model,
    x_val: pd.DataFrame,
    y_val: pd.Series,
    target_recall: float = 0.95,
) -> float:
    """Find the highest threshold that achieves >= target_recall on the val set.

    Higher threshold = better precision while meeting recall floor. Scans
    from high to low with a fine grid (step 0.005). Falls back to lowest
    threshold (maximum possible recall) if the target cannot be met.
    """
    proba = model.predict_proba(x_val)[:, 1]
    # Fine grid down to 0.005 so we can squeeze out every recall point
    thresholds = np.arange(0.005, 0.995, 0.005)

    best_t = float(thresholds[0])  # lowest = highest recall as fallback
    for t in sorted(thresholds, reverse=True):
        rec = recall_score(y_val, (proba >= t).astype(int), zero_division=0)
        if rec >= target_recall:
            best_t = float(t)
            break

    return best_t
