from __future__ import annotations

from typing import List

import pandas as pd

from .models import Parameters
from .optimizer import LineupResult
from .io_utils import write_csv, write_json


def snapshot_cleaned_projections(df: pd.DataFrame, path: str = "artifacts/cleaned_projections.csv") -> None:
    write_csv(df, path)


essential_player_cols = ["Name", "Team", "Opponent", "Position", "Salary", "Projection", "Ownership"]


def snapshot_players_pool(df: pd.DataFrame, path: str = "artifacts/players_pool.csv") -> None:
    subset_cols = [c for c in essential_player_cols if c in df.columns]
    write_csv(df[subset_cols], path)


def snapshot_lineups(lineups: List[LineupResult], path: str = "artifacts/lineups.json") -> None:
    payload = []
    for lu in lineups:
        payload.append(
            {
                "projection": lu.total_projection,
                "sum_ownership": lu.sum_ownership,
                "product_ownership": lu.product_ownership,
                "stack_positions": list(lu.stack_positions),
                "game_stack": {"key": lu.max_game_key, "count": lu.max_game_stack},
                "players": [
                    {
                        "name": p.name,
                        "team": p.team,
                        "opponent": p.opponent,
                        "position": p.position,
                        "salary": p.salary,
                        "projection": p.projection,
                        "ownership": p.ownership,
                    }
                    for p in lu.players
                ],
            }
        )
    write_json(payload, path)


def snapshot_parameters(params: Parameters, path: str = "artifacts/parameters.json") -> None:
    from dataclasses import asdict

    write_json(asdict(params), path)
