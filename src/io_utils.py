from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import json

from .logging_utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class ExcelWorkbookPaths:
    unfiltered: str
    filtered: str


def ensure_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def read_csv(path: str) -> pd.DataFrame:
    assert os.path.exists(path), f"Input file not found: {path}"
    df = pd.read_csv(path)
    logger.info("Loaded CSV: %s rows=%d cols=%d", path, len(df), df.shape[1])
    return df


def write_csv(df: pd.DataFrame, path: str) -> None:
    ensure_dir(path)
    df.to_csv(path, index=False)
    logger.info("Wrote CSV: %s rows=%d cols=%d", path, len(df), df.shape[1])


def write_excel_with_tabs(
    projections_df: pd.DataFrame,
    params_df: pd.DataFrame,
    lineups_df: pd.DataFrame,
    path: str,
    players_df: Optional[pd.DataFrame] = None,
    extra_tabs: Optional[dict[str, pd.DataFrame]] = None,
) -> None:
    ensure_dir(path)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        projections_df.to_excel(writer, sheet_name="Projections", index=False)
        params_df.to_excel(writer, sheet_name="Parameters", index=False)
        lineups_df.to_excel(writer, sheet_name="Lineups", index=False)
        if players_df is not None:
            players_df.to_excel(writer, sheet_name="Players", index=False)
        if extra_tabs:
            for sheet_name, df in extra_tabs.items():
                try:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                except Exception:
                    # If anything goes wrong, write an empty sheet to avoid breaking the export
                    pd.DataFrame().to_excel(writer, sheet_name=sheet_name, index=False)
    tabs = ["Projections", "Parameters", "Lineups"]
    if players_df is not None:
        tabs.append("Players")
    if extra_tabs:
        tabs.extend(list(extra_tabs.keys()))
    logger.info("Wrote Excel workbook: %s (tabs: %s)", path, ", ".join(tabs))


def write_json(obj, path: str) -> None:
    ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    logger.info("Wrote JSON: %s", path)


