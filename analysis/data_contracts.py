"""
Data contracts and fail-fast dataset validation for MVP pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class ColumnRule:
    name: str
    required: bool = True
    allow_nulls: bool = True
    numeric_range: Optional[Tuple[float, float]] = None


@dataclass(frozen=True)
class DatasetContract:
    dataset_name: str
    rules: Tuple[ColumnRule, ...]


class DataContractError(ValueError):
    pass


RIDERSHIP_CONTRACT = DatasetContract(
    dataset_name="ridership_clean.csv",
    rules=(
        ColumnRule("date", allow_nulls=False),
        ColumnRule("year", allow_nulls=False, numeric_range=(2020, 2035)),
        ColumnRule("month", allow_nulls=False, numeric_range=(1, 12)),
    ),
)

CRIME_CONTRACT = DatasetContract(
    dataset_name="crime_clean.csv",
    rules=(
        ColumnRule("date", allow_nulls=False),
        ColumnRule("year", allow_nulls=False, numeric_range=(2020, 2035)),
        ColumnRule("month", allow_nulls=False, numeric_range=(1, 12)),
        ColumnRule("station_name", allow_nulls=False),
        ColumnRule("boro_nm", allow_nulls=True),
        ColumnRule("ofns_desc", allow_nulls=False),
    ),
)

ELEVATOR_CONTRACT = DatasetContract(
    dataset_name="elevator_clean.csv",
    rules=(
        ColumnRule("month", allow_nulls=False),
        ColumnRule("year", allow_nulls=False, numeric_range=(2015, 2035)),
        ColumnRule("month_num", allow_nulls=False, numeric_range=(1, 12)),
        ColumnRule("equipment_code", allow_nulls=False),
        ColumnRule("equipment_type", allow_nulls=False),
        ColumnRule("borough", allow_nulls=True),
        ColumnRule("am_peak_availability", allow_nulls=True, numeric_range=(0, 100)),
        ColumnRule("unscheduled_outages", allow_nulls=True, numeric_range=(0, 10000)),
        ColumnRule("time_since_major_improvement", allow_nulls=True, numeric_range=(0, 5000)),
    ),
)


def _validate_required_columns(df: pd.DataFrame, contract: DatasetContract, errors: List[str]) -> None:
    for rule in contract.rules:
        if rule.required and rule.name not in df.columns:
            errors.append(f"Missing required column `{rule.name}` in {contract.dataset_name}.")


def _validate_nulls(df: pd.DataFrame, contract: DatasetContract, errors: List[str]) -> None:
    for rule in contract.rules:
        if rule.name not in df.columns:
            continue
        if not rule.allow_nulls and df[rule.name].isna().any():
            errors.append(f"Column `{rule.name}` contains null values in {contract.dataset_name}.")


def _validate_numeric_ranges(df: pd.DataFrame, contract: DatasetContract, errors: List[str]) -> None:
    for rule in contract.rules:
        if rule.name not in df.columns or rule.numeric_range is None:
            continue
        lo, hi = rule.numeric_range
        series = pd.to_numeric(df[rule.name], errors="coerce")
        bad = series[(~series.isna()) & ((series < lo) | (series > hi))]
        if not bad.empty:
            errors.append(
                f"Column `{rule.name}` has out-of-range values in {contract.dataset_name}. "
                f"Expected [{lo}, {hi}], found min={series.min()} max={series.max()}."
            )


def validate_dataframe_contract(df: pd.DataFrame, contract: DatasetContract) -> None:
    errors: List[str] = []
    _validate_required_columns(df, contract, errors)
    _validate_nulls(df, contract, errors)
    _validate_numeric_ranges(df, contract, errors)
    if errors:
        raise DataContractError("\n".join(errors))


def validate_clean_datasets(clean_frames: Dict[str, pd.DataFrame]) -> None:
    contract_map = {
        RIDERSHIP_CONTRACT.dataset_name: RIDERSHIP_CONTRACT,
        CRIME_CONTRACT.dataset_name: CRIME_CONTRACT,
        ELEVATOR_CONTRACT.dataset_name: ELEVATOR_CONTRACT,
    }
    for filename, contract in contract_map.items():
        if filename not in clean_frames:
            raise DataContractError(f"Missing dataframe for contract validation: {filename}")
        validate_dataframe_contract(clean_frames[filename], contract)


def require_columns(df: pd.DataFrame, columns: Iterable[str], dataset_name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise DataContractError(f"{dataset_name} missing required columns: {missing}")
