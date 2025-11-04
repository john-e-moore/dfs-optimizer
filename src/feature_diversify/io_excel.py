from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import os
import re

import pandas as pd


DEFAULT_SHEET_NAME = "Lineups"


@dataclass(frozen=True)
class SourceKey:
    path: str
    sheet: Optional[str] = None

    def key(self, default_sheet: str = DEFAULT_SHEET_NAME) -> str:
        return f"{self.path}:{self.sheet or default_sheet}"


@dataclass
class LineupRecord:
    source_key: str
    row_index: int
    projection: Optional[float]
    player_tokens: Set[str]
    original_row: pd.Series


ROSTER_COLS_CANONICAL: Tuple[str, ...] = (
    "QB",
    "RB1",
    "RB2",
    "WR1",
    "WR2",
    "WR3",
    "TE",
    "FLEX",
    "DST",
)


def parse_source_key(spec: str) -> SourceKey:
    if ":" in spec:
        path, sheet = spec.split(":", 1)
        path = path.strip()
        sheet = sheet.strip() or None
        return SourceKey(path=path, sheet=sheet)
    return SourceKey(path=spec.strip(), sheet=None)


def _extract_name_team(value: object) -> Tuple[str, Optional[str]]:
    s = str(value) if value is not None else ""
    s = s.strip()
    if not s:
        return "", None
    # Expect formats like "Player Name (TEAM)"; fall back to the whole string as name
    if s.endswith(")") and "(" in s:
        try:
            name, team_with_paren = s.rsplit(" (", 1)
            team = team_with_paren[:-1]
            return name.strip(), team.strip() or None
        except Exception:
            return s, None
    return s, None


def _normalize_player_token(name: str, team: Optional[str]) -> str:
    name = name.strip()
    if team:
        return f"{name}|{team}"
    return name


def _detect_roster_columns(df: pd.DataFrame, explicit: Optional[Sequence[str]] = None) -> Optional[List[str]]:
    if explicit:
        cols = [c for c in explicit if c in df.columns]
        return cols if len(cols) >= 7 else None
    present = [c for c in ROSTER_COLS_CANONICAL if c in df.columns]
    # Require enough slots to form a lineup (most sheets should have all 9)
    if len(present) >= 7:
        return present
    return None


def _extract_players_from_row(row: pd.Series, roster_cols: Sequence[str]) -> Set[str]:
    tokens: Set[str] = set()
    for c in roster_cols:
        if c not in row.index:
            continue
        name, team = _extract_name_team(row[c])
        if not name:
            continue
        tokens.add(_normalize_player_token(name, team))
    return tokens


def _extract_players_from_players_col(row: pd.Series, players_col: str) -> Set[str]:
    value = row.get(players_col)
    if value is None:
        return set()
    items = [s.strip() for s in str(value).split(",") if s.strip()]
    tokens: Set[str] = set()
    for s in items:
        name, team = _extract_name_team(s)
        if not name:
            continue
        tokens.add(_normalize_player_token(name, team))
    return tokens


def read_lineups_from_source(
    source: SourceKey,
    *,
    default_sheet: str = DEFAULT_SHEET_NAME,
    roster_cols: Optional[Sequence[str]] = None,
    players_col: Optional[str] = None,
    projection_col: str = "Projection",
) -> List[LineupRecord]:
    sheet = source.sheet or default_sheet
    if not os.path.exists(source.path):
        # Return empty; caller will decide how to handle missing sources
        return []
    try:
        df = pd.read_excel(source.path, sheet_name=sheet)
    except Exception:
        return []

    # Try roster columns first
    detected_roster = _detect_roster_columns(df, explicit=roster_cols)
    using_players_col = False
    if not detected_roster:
        # Try players column
        if players_col and players_col in df.columns:
            using_players_col = True
        else:
            # Heuristic: case-insensitive match for 'players'
            for c in df.columns:
                if str(c).strip().lower() == "players":
                    players_col = c
                    using_players_col = True
                    break
        if not using_players_col:
            return []

    recs: List[LineupRecord] = []
    skey = source.key(default_sheet)
    for idx, row in df.iterrows():
        try:
            if using_players_col:
                player_tokens = _extract_players_from_players_col(row, assert_not_none(players_col))
            else:
                player_tokens = _extract_players_from_row(row, assert_not_none(detected_roster))
            if len(player_tokens) == 0:
                continue
            proj = None
            if projection_col in df.columns:
                try:
                    proj_val = row[projection_col]
                    proj = float(proj_val) if pd.notna(proj_val) else None
                except Exception:
                    proj = None
            recs.append(
                LineupRecord(
                    source_key=skey,
                    row_index=int(idx),
                    projection=proj,
                    player_tokens=player_tokens,
                    original_row=row,
                )
            )
        except Exception:
            # Skip malformed rows
            continue
    return recs


def assert_not_none(value: Optional[Sequence[str] | str]) -> Sequence[str] | str:
    if value is None:
        raise ValueError("Unexpected None where a value was required")
    return value


def read_lineups_from_sources(
    sources: Iterable[SourceKey],
    *,
    default_sheet: str = DEFAULT_SHEET_NAME,
    roster_cols: Optional[Sequence[str]] = None,
    players_col: Optional[str] = None,
    projection_col: str = "Projection",
) -> List[LineupRecord]:
    all_recs: List[LineupRecord] = []
    for s in sources:
        all_recs.extend(
            read_lineups_from_source(
                s,
                default_sheet=default_sheet,
                roster_cols=roster_cols,
                players_col=players_col,
                projection_col=projection_col,
            )
        )
    return all_recs


