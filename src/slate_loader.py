from __future__ import annotations

import os
import glob
import json
from typing import Dict, Tuple, Optional
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
