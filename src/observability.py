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
        # Classic mode (optimizer.LineupResult) has 'players' and stack metadata.
        if hasattr(lu, "players"):
            payload.append(
                {
                    "mode": "classic",
                    "projection": lu.total_projection,
                    "sum_ownership": lu.sum_ownership,
                    "product_ownership": lu.product_ownership,
                    "stack_positions": list(getattr(lu, "stack_positions", ())),
                    "game_stack": {"key": getattr(lu, "max_game_key", ""), "count": getattr(lu, "max_game_stack", 0)},
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
        # Showdown mode has 'entries' with role information.
        elif hasattr(lu, "entries"):
            payload.append(
                {
                    "mode": "showdown",
                    "projection": getattr(lu, "total_projection", None),
                    "sum_ownership": getattr(lu, "sum_ownership", None),
                    "product_ownership": getattr(lu, "product_ownership", None),
                    "players": [
                        {
                            "name": e.name,
                            "team": e.team,
                            "opponent": e.opponent,
                            "position": e.position,
                            "role": getattr(e, "role", ""),
                            "salary": e.salary,
                            "projection": e.projection,
                            "ownership": e.ownership,
                        }
                        for e in lu.entries
                    ],
                }
            )
        else:
            # Fallback minimal payload
            payload.append(
                {
                    "projection": getattr(lu, "total_projection", None),
                    "sum_ownership": getattr(lu, "sum_ownership", None),
                    "product_ownership": getattr(lu, "product_ownership", None),
                }
            )
    write_json(payload, path)


def snapshot_parameters(params: Parameters, path: str = "artifacts/parameters.json") -> None:
    from dataclasses import asdict
    def _json_safe(obj):
        if isinstance(obj, set):
            return sorted(list(obj))
        if isinstance(obj, tuple):
            return [_json_safe(x) for x in obj]
        if isinstance(obj, list):
            return [_json_safe(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): _json_safe(v) for k, v in obj.items()}
        return obj

    data = asdict(params)
    safe = _json_safe(data)
    write_json(safe, path)


