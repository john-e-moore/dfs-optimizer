from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .models import Parameters
from .io_utils import write_excel_with_tabs
from .dk_upload import (
    load_dk_entries,
    format_lineups_for_dk,
    build_name_to_id_map_from_projections,
)


def build_parameters_df(params: Parameters) -> pd.DataFrame:
    data: Dict[str, Any] = dataclasses.asdict(params)
    # Keep order stable for readability
    ordered_keys = [
        "lineup_count",
        "min_salary",
        "allow_qb_vs_dst",
        "allow_rb_vs_dst",
        "stack",
        "game_stack",
        "min_sum_projection",
        "max_sum_projection",
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
    # New layout: one parameter per row
    rows = []
    for k in ordered_keys:
        v = data.get(k)
        # Convert collections to readable strings
        if isinstance(v, set):
            v = ", ".join(sorted(v))
        elif isinstance(v, dict):
            v = ", ".join(f"{kk}:{vv}" for kk, vv in sorted(v.items()))
        rows.append({"Parameter": k, "Value": v})
    return pd.DataFrame(rows, columns=["Parameter", "Value"])


def export_workbook(
    projections_df: pd.DataFrame,
    params: Parameters,
    lineups_df: pd.DataFrame,
    path: str,
    *,
    start_time_map: Optional[Dict[Tuple[str, str], int]] = None,
    games_df: Optional[pd.DataFrame] = None,
) -> None:
    params_df = build_parameters_df(params)
    players_df = build_players_exposure_df(lineups_df, projections_df, start_time_map=start_time_map)
    try:
        name_to_id_override = None
        if "DFS ID" in projections_df.columns:
            name_to_id_override = build_name_to_id_map_from_projections(projections_df)
        # Load DK entries unless we have a complete override
        dk_entries = load_dk_entries() if name_to_id_override is None else pd.DataFrame()
        dk_lineups_df = format_lineups_for_dk(
            lineups_df,
            projections_df,
            dk_entries,
            name_to_id_override=name_to_id_override,
        )
        extra_tabs: Dict[str, pd.DataFrame] = {"DK Lineups": dk_lineups_df}
    except Exception:
        # Be resilient; if anything fails in DK mapping, proceed without the extra tab
        extra_tabs = {}
    # Add Games tab when provided
    if games_df is not None:
        try:
            extra_tabs["Games"] = games_df
        except Exception:
            pass
    write_excel_with_tabs(projections_df, params_df, lineups_df, path, players_df=players_df, extra_tabs=extra_tabs or None)


def build_players_exposure_df(
    lineups_df: pd.DataFrame,
    projections_df: pd.DataFrame,
    *,
    start_time_map: Optional[Dict[Tuple[str, str], int]] = None,
) -> pd.DataFrame:
    if lineups_df is None or lineups_df.empty:
        return pd.DataFrame({"Player": [], "Position": [], "Team": [], "# Lineups": [], "% Lineups": [], "Start Time": []})
    classic_cols = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
    showdown_cols = ["CPT", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"]
    player_cols = classic_cols + showdown_cols
    present_cols = [c for c in player_cols if c in lineups_df.columns]
    if not present_cols:
        return pd.DataFrame({"Player": [], "Position": [], "Team": [], "# Lineups": [], "% Lineups": [], "Start Time": []})

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
        # Look up start time using (NAME, TEAM) with uppercase matching
        start_str = ""
        if start_time_map is not None and team:
            key = (str(name).upper().strip(), str(team).upper().strip())
            epoch = start_time_map.get(key)
            if epoch is not None:
                try:
                    ts = pd.to_datetime(int(epoch), unit="s", utc=True).tz_convert("US/Eastern")
                    start_str = ts.strftime("%Y-%m-%d %H:%M ET")
                except Exception:
                    start_str = ""
        records.append({
            "Player": name,
            "Position": pos,
            "Team": team,
            "# Lineups": int(cnt),
            "% Lineups": pct,
            "Start Time": start_str,
        })

    out = pd.DataFrame.from_records(records)
    out = out.sort_values(by=["# Lineups", "Player"], ascending=[False, True]).reset_index(drop=True)
    return out


