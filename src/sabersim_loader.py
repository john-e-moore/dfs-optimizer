from __future__ import annotations

import glob
import os
from typing import Dict, List, Tuple

import pandas as pd

from .logging_utils import setup_logger
from .data_loader import normalize_ownership

logger = setup_logger(__name__)


def find_latest_sabersim_csv(directory: str = "data/", prefix: str = "NFL_") -> str:
    pattern = os.path.join(directory, f"{prefix}*.csv")
    candidates = glob.glob(pattern)
    candidates = [p for p in candidates if os.path.isfile(p)]
    if not candidates:
        raise FileNotFoundError(
            f"No SaberSim CSV files found matching '{pattern}'. Place an '{prefix}*.csv' under {directory}."
        )
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    latest = candidates[0]
    logger.info("Using SaberSim CSV: %s", latest)
    return latest


def _normalize_headers(columns: List[str]) -> List[str]:
    return [str(c).strip() for c in columns]


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def load_and_clean_sabersim_csv(path: str) -> pd.DataFrame:
    assert os.path.exists(path), f"Input file not found: {path}"
    df = pd.read_csv(path)
    df.columns = _normalize_headers(list(df.columns))

    # Column aliases
    aliases: Dict[str, Tuple[str, ...]] = {
        "Name": ("Name",),
        "Team": ("Team",),
        "Opponent": ("Opponent", "Opp"),
        "Position": ("Position", "Pos"),
        "Salary": ("Salary",),
        "Projection": ("SS Proj",),
        "Ownership": ("Adj Own",),
        "DFS ID": ("DFS ID",),
    }

    def pick(colnames: Tuple[str, ...]) -> str | None:
        for c in colnames:
            if c in df.columns:
                return c
        return None

    mapping: Dict[str, str] = {}
    missing: List[str] = []
    for target, candidates in aliases.items():
        src = pick(candidates)
        if src is None:
            # Only DFS ID is optional in cleaned projection schema; others are required
            if target == "DFS ID":
                continue
            missing.append(target)
        else:
            mapping[target] = src

    if missing:
        raise ValueError(
            "Missing required SaberSim columns: " + ", ".join(missing) +
            ". Ensure the workbook includes Name, Team, Opponent/Opp, Position/Pos, Salary, SS Proj, Adj Own."
        )

    out = pd.DataFrame()
    out["Name"] = df[mapping["Name"]].astype(str)
    out["Team"] = df[mapping["Team"]].astype(str).str.upper().str.strip()
    out["Opponent"] = df[mapping["Opponent"]].astype(str).str.upper().str.strip()
    out["Position"] = df[mapping["Position"]].astype(str).str.upper().str.strip()
    out["Salary"] = _coerce_numeric(df[mapping["Salary"]])
    out["Projection"] = _coerce_numeric(df[mapping["Projection"]])
    out["Ownership"] = _coerce_numeric(df[mapping["Ownership"]])
    # Normalize ownership to 0..1
    out["Ownership"] = normalize_ownership(out["Ownership"])

    # Carry-through DFS ID for DK mapping override (optional)
    if "DFS ID" in mapping:
        out["DFS ID"] = df[mapping["DFS ID"]].astype(str).str.strip()

    # Drop rows with missing required canonical fields
    before = len(out)
    out = out.dropna(subset=["Name", "Team", "Opponent", "Position", "Salary", "Projection", "Ownership"]).copy()
    after = len(out)
    if after < before:
        logger.info("SaberSim cleaner dropped %d rows due to missing values", before - after)

    # Basic sanity checks similar to CSV cleaner
    assert out["Salary"].ge(0).all(), "Salary must be non-negative"
    assert out["Projection"].ge(0).all(), "Projection must be non-negative"

    logger.info("Loaded SaberSim: %s rows=%d cols=%d", path, len(out), out.shape[1])
    return out


