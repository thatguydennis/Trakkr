"""
clean_data.py
Cleans all three raw datasets and outputs analysis-ready CSVs to data/clean/
"""

import os

import numpy as np
import pandas as pd

from artifacts import copy_to_run_dir, create_run_context, update_latest_pointer, write_run_metadata
from data_contracts import validate_clean_datasets

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw")
CLEAN = os.path.join(BASE, "data", "clean")

# Prefer fresh download; fall back to original
_ELEV_FRESH = os.path.join(RAW, "elevator_escalator_availability_fresh.csv")
_ELEV_ORIG  = os.path.join(RAW, "elevator_escalator_availability.csv")
ELEV_RAW    = _ELEV_FRESH if os.path.exists(_ELEV_FRESH) else _ELEV_ORIG


def _clean_ridership():
    df = pd.read_csv(os.path.join(RAW, "mta_daily_ridership.csv"))
    df.columns = [
        c.strip().lower().replace(" ", "_").replace(":", "").replace("%", "pct")
         .replace("/", "_").replace("-", "_")
        for c in df.columns
    ]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for col in df.columns:
        if df[col].dtype == object and col != "date":
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("%", "").str.strip(),
                errors="coerce",
            )
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.strftime("%b")
    df["day_of_week"] = df["date"].dt.day_name()
    df["is_weekend"] = df["day_of_week"].isin(["Saturday", "Sunday"])
    return df[df["year"].between(2020, 2026)]


def _clean_crime():
    # Load 2020-2024 baseline
    cr = pd.read_csv(os.path.join(RAW, "nypd_transit_crime.csv"), low_memory=False)
    cr.columns = [c.strip().lower().replace(" ", "_") for c in cr.columns]
    cr["cmplnt_fr_dt"] = pd.to_datetime(cr["cmplnt_fr_dt"], errors="coerce")
    cr = cr.dropna(subset=["cmplnt_fr_dt"]).rename(columns={"cmplnt_fr_dt": "date"})

    # Append each supplemental crime file in order
    for fname, min_year in [("nypd_crime_2025_2026.csv", 2025), ("nypd_crime_q1_2026.csv", 2026)]:
        fpath = os.path.join(RAW, fname)
        if os.path.exists(fpath):
            extra = pd.read_csv(fpath, low_memory=False)
            extra.columns = [c.strip().lower().replace(" ", "_") for c in extra.columns]
            extra["cmplnt_fr_dt"] = pd.to_datetime(extra["cmplnt_fr_dt"], errors="coerce")
            extra = extra.dropna(subset=["cmplnt_fr_dt"]).rename(columns={"cmplnt_fr_dt": "date"})
            extra = extra[extra["date"].dt.year >= min_year]
            cr = pd.concat([cr, extra], ignore_index=True)

    cr["year"] = cr["date"].dt.year
    cr["month"] = cr["date"].dt.month
    cr["month_year"] = cr["date"].dt.to_period("M").astype(str)
    cr = cr[cr["year"].between(2020, 2026)]

    for col in ["ofns_desc", "pd_desc", "law_cat_cd", "boro_nm", "station_name"]:
        if col in cr.columns:
            cr[col] = cr[col].astype(str).str.strip().str.upper()

    # Drop nulls and placeholder strings
    cr = cr[
        cr["ofns_desc"].notna() & (cr["ofns_desc"] != "NAN") &
        cr["station_name"].notna() & (cr["station_name"] != "NAN") &
        (cr["station_name"] != "(NULL)")
    ]
    return cr.drop_duplicates().reset_index(drop=True)


def _clean_station_ridership():
    """Load station ridership map (MTA → NYPD matched) and fill missing stations
    with their borough-level average so every NYPD station gets a ridership value."""
    rid_path = os.path.join(RAW, "station_ridership_2025.csv")
    if not os.path.exists(rid_path):
        return None
    rid = pd.read_csv(rid_path)
    rid["avg_monthly_ridership"] = pd.to_numeric(rid["avg_monthly_ridership"], errors="coerce")
    rid["station_name"] = rid["station_name"].astype(str).str.strip().str.upper()
    return rid


def _clean_elevator():
    df = pd.read_csv(ELEV_RAW, low_memory=False)
    df.columns = [
        c.strip().lower().replace(" ", "_").replace("/", "_")
        for c in df.columns
    ]
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    df = df.dropna(subset=["month"])
    df["year"] = df["month"].dt.year
    df["month_num"] = df["month"].dt.month
    df = df[df["year"].between(2015, 2026)]

    for col in ["total_outages", "scheduled_outages", "unscheduled_outages", "entrapments",
                "time_since_major_improvement"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    for col in ["am_peak_availability", "pm_peak_availability", "24-hour_availability"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace("%", "").str.strip(),
                errors="coerce",
            )

    # Normalize station_name to uppercase for consistency
    for col in ["station_name", "station_complex_name", "borough", "equipment_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def main():
    os.makedirs(CLEAN, exist_ok=True)

    print(f"Cleaning ridership data...")
    df_ride = _clean_ridership()
    print(f"  → {len(df_ride):,} rows | {df_ride['date'].min().date()} to {df_ride['date'].max().date()}")
    ridership_out = os.path.join(CLEAN, "ridership_clean.csv")
    df_ride.to_csv(ridership_out, index=False)

    print("Cleaning NYPD transit crime data...")
    df_crime = _clean_crime()
    print(f"  → {len(df_crime):,} rows | {df_crime['date'].min().date()} to {df_crime['date'].max().date()}")
    print(f"  → Unique stations: {df_crime['station_name'].nunique()} | Years: {sorted(df_crime['year'].unique())}")
    crime_out = os.path.join(CLEAN, "crime_clean.csv")
    df_crime.to_csv(crime_out, index=False)

    print(f"Cleaning elevator/escalator data (source: {os.path.basename(ELEV_RAW)})...")
    df_elev = _clean_elevator()
    print(f"  → {len(df_elev):,} rows | {df_elev['month'].min().date()} to {df_elev['month'].max().date()}")
    print(f"  → Equipment codes: {df_elev['equipment_code'].nunique()} | Stations: {df_elev['station_name'].nunique()}")
    elev_out = os.path.join(CLEAN, "elevator_clean.csv")
    df_elev.to_csv(elev_out, index=False)

    df_station_rid = _clean_station_ridership()
    if df_station_rid is not None:
        station_rid_out = os.path.join(CLEAN, "station_ridership.csv")
        df_station_rid.to_csv(station_rid_out, index=False)
        print(f"Station ridership map: {len(df_station_rid)} stations → {station_rid_out}")

    print("Validating clean dataset contracts...")
    validate_clean_datasets({"ridership_clean.csv": df_ride, "crime_clean.csv": df_crime, "elevator_clean.csv": df_elev})
    print("  ✓ contracts passed")

    ctx = create_run_context("clean_data")
    copy_to_run_dir(ctx, ridership_out)
    copy_to_run_dir(ctx, crime_out)
    copy_to_run_dir(ctx, elev_out)
    write_run_metadata(ctx, {
        "status": "success",
        "elevator_source": os.path.basename(ELEV_RAW),
        "raw_dir": RAW,
        "clean_dir": CLEAN,
        "row_counts": {
            "ridership_clean.csv": int(len(df_ride)),
            "crime_clean.csv": int(len(df_crime)),
            "elevator_clean.csv": int(len(df_elev)),
        },
        "date_ranges": {
            "ridership_clean.csv": [str(df_ride["date"].min().date()), str(df_ride["date"].max().date())],
            "crime_clean.csv": [str(df_crime["date"].min().date()), str(df_crime["date"].max().date())],
            "elevator_clean.csv": [str(df_elev["month"].min().date()), str(df_elev["month"].max().date())],
        },
    })
    update_latest_pointer(ctx)
    print(f"\nAll datasets cleaned. Files in data/clean/ and versioned run at {ctx.run_dir}")


if __name__ == "__main__":
    main()
