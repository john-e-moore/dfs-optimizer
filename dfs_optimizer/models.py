from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import pandas as pd

ALLOWED_POSITIONS = {"QB", "RB", "WR", "TE", "DST"}


@dataclass(frozen=True)
class Player:
    name: str
    team: str
    opponent: str
    position: str
    salary: int
    projection: float
    ownership: float

    def display_name(self) -> str:
        return f"{self.name} ({self.team})"


@dataclass
class Parameters:
    lineup_count: int = 5000
    min_salary: int = 45000
    allow_qb_vs_dst: bool = False
    stack: int = 1
    game_stack: int = 0
    # New constraints/filters
    excluded_players: Set[str] = field(default_factory=set)
    included_players: Set[str] = field(default_factory=set)
    excluded_teams: Set[str] = field(default_factory=set)
    min_players_by_team: Dict[str, int] = field(default_factory=dict)
    rb_dst_stack: bool = False
    # Lineup-level projection filter (replaces per-player projection)
    min_sum_projection: Optional[float] = None
    min_player_projection: Optional[float] = None
    min_sum_ownership: Optional[float] = None
    max_sum_ownership: Optional[float] = None
    min_product_ownership: Optional[float] = None
    max_product_ownership: Optional[float] = None
    # Performance tuning
    solver_threads: Optional[int] = None
    solver_time_limit_s: Optional[int] = None

    def validate(self) -> None:
        assert self.lineup_count > 0
        assert 0 <= self.min_salary <= 50000
        assert self.stack >= 0
        assert self.game_stack >= 0
        # Basic sanity for new params (detailed feasibility checks handled elsewhere)
        for k, v in self.min_players_by_team.items():
            assert isinstance(k, str) and k, "Team key must be non-empty string"
            assert isinstance(v, int) and v >= 0, "Minimum players by team must be non-negative integer"
        if self.min_sum_ownership is not None and self.max_sum_ownership is not None:
            assert self.min_sum_ownership <= self.max_sum_ownership
        if self.min_product_ownership is not None and self.max_product_ownership is not None:
            assert self.min_product_ownership <= self.max_product_ownership
        if self.solver_threads is not None:
            assert self.solver_threads > 0
        if self.solver_time_limit_s is not None:
            assert self.solver_time_limit_s > 0


def game_key(team: str, opponent: str) -> str:
    parts = sorted([team.upper(), opponent.upper()])
    return "-".join(parts)


def players_from_df(df: pd.DataFrame) -> List[Player]:
    required = ["Name", "Team", "Opponent", "Position", "Salary", "Projection", "Ownership"]
    missing = [c for c in required if c not in df.columns]
    assert not missing, f"Missing columns for players: {missing}"

    players: List[Player] = []
    for _, row in df.iterrows():
        position = str(row["Position"]).upper()
        assert position in ALLOWED_POSITIONS, f"Invalid position: {position}"
        salary = int(row["Salary"])  # may raise if NaN; desired
        projection = float(row["Projection"])
        ownership = float(row["Ownership"])
        assert 0 <= ownership <= 1, "Ownership must be fraction in [0,1]"
        players.append(
            Player(
                name=str(row["Name"]),
                team=str(row["Team"]).upper(),
                opponent=str(row["Opponent"]).upper(),
                position=position,
                salary=salary,
                projection=projection,
                ownership=ownership,
            )
        )
    return players
