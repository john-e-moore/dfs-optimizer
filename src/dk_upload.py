from __future__ import annotations

import csv
from typing import Dict, List, Optional, Set

import pandas as pd


DK_ENTRIES_HEADER_PREFIX = [
    "Position",
    "Name + ID",
    "Name",
    "ID",
    "Roster Position",
    "Salary",
    "Game Info",
    "TeamAbbrev",
    "AvgPointsPerGame",
]


def _normalize_string(value: object) -> str:
    s = str(value) if value is not None else ""
    return s.strip()


def load_dk_entries(csv_path: str = "data/DKEntries.csv") -> pd.DataFrame:
    """
    Load DK entries by scanning for the header row that begins with the known DK columns
    and parsing all subsequent rows under that header. Returns a DataFrame with columns:
    Name (str), ID (str), Position (str), TeamAbbrev (str)
    """
    rows: List[List[str]] = []
    header: Optional[List[str]] = None
    start_idx: Optional[int] = None
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for parts in reader:
            if not parts:
                continue
            # Identify header slice anywhere in the row
            if header is None:
                n = len(DK_ENTRIES_HEADER_PREFIX)
                for j in range(0, max(0, len(parts) - n + 1)):
                    window = [p.strip() for p in parts[j : j + n]]
                    if window == DK_ENTRIES_HEADER_PREFIX:
                        header = window
                        start_idx = j
                        break
                # If we just found header in this row, skip to next row for data
                if header is not None:
                    continue
                else:
                    # Not a header row; continue scanning
                    continue
            # Collect data rows aligned to header start
            assert start_idx is not None
            # Some rows may be shorter; pad
            segment = parts[start_idx : start_idx + len(DK_ENTRIES_HEADER_PREFIX)]
            segment = (segment + [""] * len(DK_ENTRIES_HEADER_PREFIX))[: len(DK_ENTRIES_HEADER_PREFIX)]
            rows.append([p.strip() for p in segment])

    if not header:
        # If header not found, return empty DataFrame with expected columns
        return pd.DataFrame({"Name": [], "ID": [], "Position": [], "TeamAbbrev": []})

    df_full = pd.DataFrame(rows, columns=header)
    # Normalize and filter
    for c in ("Name", "ID", "Position", "TeamAbbrev"):
        if c not in df_full.columns:
            df_full[c] = ""
        df_full[c] = df_full[c].astype(str).map(_normalize_string)

    df = df_full[["Name", "ID", "Position", "TeamAbbrev"]].copy()
    # Drop blank names and blank IDs (we still keep rows for DST fallback if needed, but prefer non-empty IDs)
    return df


def build_name_to_id_map(dk_df: pd.DataFrame) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for _, row in dk_df.iterrows():
        name = _normalize_string(row.get("Name", ""))
        pid = _normalize_string(row.get("ID", ""))
        if not name or not pid:
            continue
        if name not in mapping:
            mapping[name] = pid
    return mapping


def build_name_to_id_map_from_projections(df: pd.DataFrame, id_col: str = "DFS ID") -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if df is None or df.empty or id_col not in df.columns or "Name" not in df.columns:
        return mapping
    for _, row in df.iterrows():
        name = _normalize_string(row.get("Name", ""))
        pid = _normalize_string(row.get(id_col, ""))
        if not name or not pid:
            continue
        if name not in mapping:
            mapping[name] = pid
    return mapping


def _extract_base_name(value: object) -> str:
    s = _normalize_string(value)
    if s.endswith(")") and "(" in s:
        # Take substring before the last " ("
        try:
            return s.rsplit(" (", 1)[0].strip()
        except Exception:
            return s
    return s


def format_lineups_for_dk(
    lineups_df: pd.DataFrame,
    projections_df: pd.DataFrame,
    dk_entries_df: pd.DataFrame,
    logger: Optional[object] = None,
    name_to_id_override: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Return a copy of lineups_df where player columns are converted to "Name (ID)".
    If ID cannot be found, leave the base name as-is and record a warning later.
    """
    if lineups_df is None or lineups_df.empty:
        return lineups_df.copy()

    out = lineups_df.copy()
    # Detect classic vs showdown roster columns
    classic_cols_all = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
    showdown_cols_all = ["CPT", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"]
    is_showdown = any(c in out.columns for c in ("CPT", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"))
    player_cols = [c for c in (showdown_cols_all if is_showdown else classic_cols_all) if c in out.columns]
    if not player_cols:
        # No recognized player columns; return unchanged
        return out

    # Build name map from DK entries (and optional override)
    name_to_id = build_name_to_id_map(dk_entries_df)
    if name_to_id_override:
        # Override takes precedence
        name_to_id = {**name_to_id, **name_to_id_override}

    # Build quick lookup for positions/teams from projections
    proj = projections_df.copy()
    proj["Name"] = proj["Name"].astype(str).map(_normalize_string)
    if "Position" in proj.columns:
        proj["Position"] = proj["Position"].astype(str).map(_normalize_string)
    if "Team" in proj.columns:
        proj["Team"] = proj["Team"].astype(str).map(_normalize_string).str.upper()
    name_to_position = proj.groupby("Name")["Position"].first() if "Position" in proj.columns else {}
    name_to_team = proj.groupby("Name")["Team"].first() if "Team" in proj.columns else {}

    # DK DST lookup by team
    dk_dst_by_team: Dict[str, str] = {}
    for _, r in dk_entries_df.iterrows():
        pos = _normalize_string(r.get("Position", ""))
        team = _normalize_string(r.get("TeamAbbrev", "")).upper()
        pid = _normalize_string(r.get("ID", ""))
        if pos == "DST" and team and pid and team not in dk_dst_by_team:
            dk_dst_by_team[team] = pid

    missing: Set[str] = set()

    def resolve_id(name: str, column: str) -> Optional[str]:
        # Try exact name match first
        pid = name_to_id.get(name)
        if pid:
            return pid
        # DST fallback by team
        pos = name_to_position[name] if hasattr(name_to_position, "__contains__") and name in name_to_position else None
        if (pos == "DST") or (column == "DST"):
            team = name_to_team[name] if hasattr(name_to_team, "__contains__") and name in name_to_team else None
            if team:
                pid2 = dk_dst_by_team.get(team)
                if pid2:
                    return pid2
        return None

    for c in player_cols:
        base_names = out[c].map(_extract_base_name)
        formatted: List[str] = []
        for bn in base_names:
            if not bn:
                formatted.append(bn)
                continue
            pid = resolve_id(bn, c)
            if pid:
                formatted.append(f"{bn} ({pid})")
            else:
                formatted.append(bn)
                missing.add(bn)
        out[c] = formatted

    if missing:
        msg = f"Missing DK IDs for {len(missing)} players: {sorted(missing)}"
        try:
            if logger is not None and hasattr(logger, "warning"):
                logger.warning(msg)
            else:
                # Fallback to print if logger not provided
                print(msg)
        except Exception:
            pass

    return out


