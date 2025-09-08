from __future__ import annotations

import dataclasses
from typing import Any, Dict

import pandas as pd

from .models import Parameters
from .io_utils import write_excel_with_tabs


def build_parameters_df(params: Parameters) -> pd.DataFrame:
    data: Dict[str, Any] = dataclasses.asdict(params)
    # Keep order stable for readability
    ordered_keys = [
        "lineup_count",
        "min_salary",
        "allow_qb_vs_dst",
        "stack",
        "game_stack",
        "min_player_projection",
        "min_sum_ownership",
        "max_sum_ownership",
        "min_product_ownership",
        "max_product_ownership",
        "solver_threads",
        "solver_time_limit_s",
    ]
    row = {k: data.get(k) for k in ordered_keys}
    return pd.DataFrame([row])


def export_workbook(projections_df: pd.DataFrame, params: Parameters, lineups_df: pd.DataFrame, path: str) -> None:
    params_df = build_parameters_df(params)
    players_df = build_players_exposure_df(lineups_df)
    write_excel_with_tabs(projections_df, params_df, lineups_df, path, players_df=players_df)


def build_players_exposure_df(lineups_df: pd.DataFrame) -> pd.DataFrame:
    if lineups_df is None or lineups_df.empty:
        return pd.DataFrame({"Player": [], "# Lineups": [], "% Lineups": []})
    player_cols = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
    present_cols = [c for c in player_cols if c in lineups_df.columns]
    if not present_cols:
        return pd.DataFrame({"Player": [], "# Lineups": [], "% Lineups": []})
    names = pd.Series(dtype=object)
    for c in present_cols:
        col = lineups_df[c].dropna().astype(str)
        names = pd.concat([names, col], ignore_index=True)
    counts = names.value_counts()
    total_lineups = max(1, len(lineups_df))
    percent = (counts / total_lineups * 100).round().astype(int)
    out = pd.DataFrame({
        "Player": counts.index,
        "# Lineups": counts.values,
        "% Lineups": percent.values,
    })
    out = out.sort_values(by=["# Lineups", "Player"], ascending=[False, True]).reset_index(drop=True)
    return out
