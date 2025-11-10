from __future__ import annotations

import os
import glob
import json
from typing import Dict, Tuple, Optional, List, Set
from datetime import datetime, timezone

import pandas as pd


def find_single_json_in_data(data_dir: str = "data/") -> Optional[str]:
    # Find JSON files directly under the data directory (non-recursive)
    pattern = os.path.join(data_dir, "*.json")
    files = sorted(glob.glob(pattern))
    if len(files) == 0:
        return None
    if len(files) > 1:
        raise ValueError(
            "Expected exactly one draftables JSON in data/, found: " + ", ".join(os.path.basename(f) for f in files)
        )
    return files[0]


def _parse_start_time(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        # pandas handles many timestamp formats and timezones
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        # Convert to epoch seconds
        return int(ts.to_pydatetime().timestamp())
    except Exception:
        try:
            # Fallback: try datetime.fromisoformat for simple cases
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return None


def build_start_time_map(json_path: str) -> Dict[Tuple[str, str], int]:
    assert os.path.exists(json_path), f"Draftables JSON not found: {json_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Expect structure with a top-level 'draftables' list; be resilient otherwise
    items = payload.get("draftables", []) if isinstance(payload, dict) else []
    out: Dict[Tuple[str, str], int] = {}

    for it in items:
        try:
            comp = it.get("competition", {}) if isinstance(it, dict) else {}
            raw_time = comp.get("startTime")
            epoch = _parse_start_time(raw_time)
            if epoch is None:
                continue
            # Name fields vary; prefer 'displayName', fallback to 'name'
            name_val = it.get("displayName") or it.get("name")
            team_val = it.get("teamAbbreviation") or it.get("team")
            if not name_val or not team_val:
                continue
            key = (str(name_val).upper().strip(), str(team_val).upper().strip())
            # Keep the latest time if duplicates appear; otherwise set
            prev = out.get(key)
            if prev is None or epoch > prev:
                out[key] = epoch
        except Exception:
            # Skip malformed entries
            continue

    return out


def _format_et(epoch_seconds: Optional[int], with_date: bool = True) -> str:
    if epoch_seconds is None:
        return ""
    try:
        ts = pd.to_datetime(int(epoch_seconds), unit="s", utc=True)
        et = ts.tz_convert("US/Eastern")
        if with_date:
            return et.strftime("%Y-%m-%d %H:%M ET")
        return et.strftime("%H:%M ET")
    except Exception:
        return ""


def extract_games_table(json_path: str) -> pd.DataFrame:
    """
    Build a Games dataframe with columns: Visiting, Home, Day, Time (ET),
    derived from the draftables JSON's competition blocks.
    """
    assert os.path.exists(json_path), f"Draftables JSON not found: {json_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    items = payload.get("draftables", []) if isinstance(payload, dict) else []

    # Group teams by competition key; prefer competition.id when available, else (startTime, serialized teams set)
    comps: Dict[str, Dict[str, object]] = {}
    comp_to_teams: Dict[str, Set[str]] = {}
    comp_to_home_flags: Dict[str, Dict[str, bool]] = {}

    def _comp_key(it: dict) -> str:
        comp = it.get("competition", {}) if isinstance(it, dict) else {}
        cid = comp.get("id") or comp.get("competitionId")
        st = comp.get("startTime")
        # Build a stable key string
        return str(cid) if cid is not None else f"ts::{st}"

    for it in items:
        if not isinstance(it, dict):
            continue
        comp = it.get("competition", {}) if isinstance(it, dict) else {}
        key = _comp_key(it)
        if key not in comps:
            comps[key] = comp
            comp_to_teams[key] = set()
            comp_to_home_flags[key] = {}
        team = it.get("teamAbbreviation") or it.get("team")
        if team:
            team_u = str(team).upper().strip()
            comp_to_teams[key].add(team_u)
            # Capture home flag if present on either the draftable or inside competition mapping
            is_home = it.get("isHome")
            if isinstance(is_home, bool):
                comp_to_home_flags[key][team_u] = is_home

    # Build rows
    records: List[Dict[str, object]] = []
    for key, comp in comps.items():
        st_epoch = _parse_start_time(comp.get("startTime")) if isinstance(comp, dict) else None
        teams = sorted(list(comp_to_teams.get(key, [])))
        visiting, home = "", ""
        if len(teams) >= 2:
            # Try to infer home via flags
            flags = comp_to_home_flags.get(key, {})
            home_candidates = [t for t, is_h in flags.items() if is_h]
            if home_candidates:
                home = home_candidates[0]
                visiting = teams[0] if teams[0] != home else teams[1]
            else:
                # Final fallback: alphabetical order
                visiting, home = teams[0], teams[1]
        day = ""
        time_str = ""
        if st_epoch is not None:
            try:
                ts = pd.to_datetime(int(st_epoch), unit="s", utc=True).tz_convert("US/Eastern")
                day = ts.strftime("%Y-%m-%d")
                time_str = ts.strftime("%H:%M ET")
            except Exception:
                pass
        records.append({
            "Visiting": visiting,
            "Home": home,
            "Day": day,
            "Time": time_str,
        })

    # Deduplicate by Visiting+Home+Day+Time in case multiple competition keys collapse
    if records:
        df = pd.DataFrame.from_records(records)
        df = df.drop_duplicates(subset=["Visiting", "Home", "Day", "Time"]).reset_index(drop=True)
        # Sort by date/time
        if "Day" in df.columns and "Time" in df.columns:
            try:
                sort_key = pd.to_datetime(df["Day"] + " " + df["Time"].str.replace(" ET", ""), errors="coerce")
                df = df.assign(_sort=sort_key).sort_values(by=["_sort", "Home", "Visiting"]).drop(columns=["_sort"]).reset_index(drop=True)
            except Exception:
                pass
        return df
    return pd.DataFrame({"Visiting": [], "Home": [], "Day": [], "Time": []})
