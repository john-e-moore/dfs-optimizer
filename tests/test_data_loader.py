import os
import pandas as pd
import pytest

from dfs_optimizer.data_loader import (
    load_raw_projections,
    validate_columns,
    clean_projections,
    load_and_clean,
    write_cleaned,
    REQUIRED_COLUMNS,
)


def make_df(**overrides):
    base = pd.DataFrame(
        {
            "Name": ["A", "B"],
            "Team": ["kc", "den"],
            "Opponent": ["den", "kc"],
            "Position": ["qb", "wr"],
            "Salary": [8000, 6000],
            "Projection": [25.5, 16.2],
            "Ownership": [12.0, 8.5],
        }
    )
    for k, v in overrides.items():
        base[k] = v
    return base


def test_validate_columns_passes():
    df = make_df()
    validate_columns(df)


def test_validate_columns_missing():
    df = make_df()
    df = df.drop(columns=["Ownership"])  # remove one required
    with pytest.raises(AssertionError):
        validate_columns(df)


def test_clean_normalizes_and_checks():
    df = make_df()
    cleaned = clean_projections(df)
    assert set(cleaned["Position"]) == {"QB", "WR"}
    assert set(cleaned["Team"]) == {"KC", "DEN"}
    assert cleaned["Ownership"].between(0, 1).all()


def test_clean_ownership_percent_to_fraction():
    df = make_df(Ownership=[50.0, 12.5])
    cleaned = clean_projections(df)
    assert pytest.approx(cleaned["Ownership"].iloc[0], 1e-6) == 0.5


def test_clean_drops_invalid_positions():
    df = make_df(Position=["Punter", "WR"])  # invalid position
    with pytest.raises(AssertionError):
        clean_projections(df)


def test_write_cleaned(tmp_path):
    out_path = tmp_path / "cleaned.csv"
    df = make_df()
    cleaned = clean_projections(df)
    write_cleaned(cleaned, str(out_path))
    assert out_path.exists()
