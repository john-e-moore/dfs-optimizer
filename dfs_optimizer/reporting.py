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
        "min_sum_projection",
        "min_sum_ownership",
        "max_sum_ownership",
        "min_product_ownership",
        "max_product_ownership",
        "excluded_players",
        "included_players",
        "excluded_teams",
        "min_players_by_team",
        "rb_dst_stack",
        "solver_threads",
        "solver_time_limit_s",
    ]
    row = {k: data.get(k) for k in ordered_keys}
    return pd.DataFrame([row])


def export_workbook(projections_df: pd.DataFrame, params: Parameters, lineups_df: pd.DataFrame, path: str) -> None:
    params_df = build_parameters_df(params)
    players_df = build_players_exposure_df(lineups_df, projections_df)
    write_excel_with_tabs(projections_df, params_df, lineups_df, path, players_df=players_df)

def build_players_exposure_df(lineups_df: pd.DataFrame, projections_df: pd.DataFrame) -> pd.DataFrame:
    if lineups_df is None or lineups_df.empty:
        return pd.DataFrame({"Player": [], "Position": [], "Team": [], "# Lineups": [], "% Lineups": []})
    player_cols = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
    present_cols = [c for c in player_cols if c in lineups_df.columns]
    if not present_cols:
        return pd.DataFrame({"Player": [], "Position": [], "Team": [], "# Lineups": [], "% Lineups": []})

    # Extract player names by stripping any trailing parenthetical (team or ownership)
    def extract_name(value: str) -> str:
        s = str(value)
        if s.endswith(")") and "(" in s:
            try:
                name_part = s.rsplit(" (", 1)[0]
                return name_part
            except Exception:
                return s
        return s

    # Build counts keyed by player name only
    name_series = pd.Series(dtype=object)
    for c in present_cols:
        col = lineups_df[c].dropna().astype(str).apply(extract_name)
        name_series = pd.concat([name_series, col], ignore_index=True)
    counts = name_series.value_counts()
    total_lineups = max(1, len(lineups_df))

    # Map name to (position, team) using projections_df
    proj = projections_df.copy()
    proj["Team"] = proj["Team"].astype(str).str.upper().str.strip()
    proj["Name"] = proj["Name"].astype(str)
    # If duplicate names exist, we take the first occurrence
    name_to_pos = proj.groupby("Name")["Position"].first()
    name_to_team = proj.groupby("Name")["Team"].first()

    records = []
    for name, cnt in counts.items():
        pos = name_to_pos.get(name, "")
        team = name_to_team.get(name, "")
        pct = int(round(cnt / total_lineups * 100))
        records.append({
            "Player": name,
            "Position": pos,
            "Team": team,
            "# Lineups": int(cnt),
            "% Lineups": pct,
        })

    out = pd.DataFrame.from_records(records)
    out = out.sort_values(by=["# Lineups", "Player"], ascending=[False, True]).reset_index(drop=True)
    return out
