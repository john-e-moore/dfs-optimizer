from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from .io_utils import read_csv, write_csv
from .logging_utils import setup_logger

logger = setup_logger(__name__)

REQUIRED_COLUMNS: Tuple[str, ...] = (
    "Name",
    "Team",
    "Opponent",
    "Position",
    "Salary",
    "Projection",
    "Ownership",
)

ALLOWED_POSITIONS = {"QB", "RB", "WR", "TE", "DST"}


def load_raw_projections(csv_path: str) -> pd.DataFrame:
    df = read_csv(csv_path)
    return df


def validate_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    assert not missing, f"Missing required columns: {missing}"


def normalize_ownership(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    if s.max() > 1.0:
        # Treat as percent 0..100
        s = s / 100.0
    assert (s >= 0).all() and (s <= 1).all(), "Ownership must be within [0,1] after normalization"
    return s


def clean_projections(df: pd.DataFrame) -> pd.DataFrame:
    validate_columns(df)

    cleaned = df.copy()

    # Normalize strings
    cleaned["Position"] = cleaned["Position"].astype(str).str.upper().str.strip()
    cleaned["Team"] = cleaned["Team"].astype(str).str.upper().str.strip()
    cleaned["Opponent"] = cleaned["Opponent"].astype(str).str.upper().str.strip()

    # Coerce numeric types
    cleaned["Salary"] = pd.to_numeric(cleaned["Salary"], errors="coerce")
    cleaned["Projection"] = pd.to_numeric(cleaned["Projection"], errors="coerce")
    cleaned["Ownership"] = pd.to_numeric(cleaned["Ownership"], errors="coerce")

    # Drop or fix invalid rows
    before = len(cleaned)
    cleaned = cleaned.dropna(subset=["Salary", "Projection", "Ownership", "Position", "Team", "Opponent", "Name"]).copy()
    after_dropna = len(cleaned)

    # Normalize ownership to 0..1
    cleaned["Ownership"] = normalize_ownership(cleaned["Ownership"])

    # Sanity checks
    assert cleaned["Salary"].ge(0).all(), "Salary must be non-negative"
    assert cleaned["Projection"].ge(0).all(), "Projection must be non-negative"
    assert cleaned["Position"].isin(ALLOWED_POSITIONS).all(), f"Positions must be one of {sorted(ALLOWED_POSITIONS)}"

    logger.info(
        "Cleaned projections: %d -> %d rows (dropna removed %d)",
        before,
        len(cleaned),
        before - after_dropna,
    )

    return cleaned


def load_and_clean(csv_path: str) -> pd.DataFrame:
    raw = load_raw_projections(csv_path)
    cleaned = clean_projections(raw)
    return cleaned


def write_cleaned(df: pd.DataFrame, out_path: str) -> None:
    write_csv(df, out_path)
