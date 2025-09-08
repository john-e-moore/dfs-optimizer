import os
import json
import pandas as pd

from dfs_optimizer.models import Player, Parameters
from dfs_optimizer.observability import (
    snapshot_cleaned_projections,
    snapshot_players_pool,
    snapshot_lineups,
    snapshot_parameters,
)
from dfs_optimizer.optimizer import LineupResult


def make_player(name: str, pos: str, team: str = "A", opp: str = "B"):
    return Player(name=name, team=team, opponent=opp, position=pos, salary=5000, projection=10.0, ownership=0.1)


def test_snapshots(tmp_path):
    df = pd.DataFrame({"Name": ["A"], "Team": ["X"], "Opponent": ["Y"], "Position": ["QB"], "Salary": [5000], "Projection": [10.0], "Ownership": [0.1]})

    p = Parameters()

    lu = LineupResult(
        players=(
            make_player("QB1", "QB"),
            make_player("RB1", "RB"),
            make_player("RB2", "RB"),
            make_player("WR1", "WR"),
            make_player("WR2", "WR"),
            make_player("WR3", "WR"),
            make_player("TE1", "TE"),
            make_player("FLEX", "WR"),
            make_player("DST1", "DST"),
        ),
        total_projection=90.0,
        total_salary=45000,
        sum_ownership=0.9,
        product_ownership=1e-6,
        stack_positions=("WR",),
        max_game_stack=4,
        max_game_key="A-B",
        stack_count=1,
        all_game_stacks=(("A-B", 4),),
        rb_dst_stack=False,
    )

    snapshot_cleaned_projections(df, str(tmp_path / "cleaned.csv"))
    snapshot_players_pool(df, str(tmp_path / "players.csv"))
    snapshot_lineups([lu], str(tmp_path / "lineups.json"))
    snapshot_parameters(p, str(tmp_path / "params.json"))

    assert (tmp_path / "cleaned.csv").exists()
    assert (tmp_path / "players.csv").exists()
    assert (tmp_path / "lineups.json").exists()
    data = json.loads((tmp_path / "lineups.json").read_text())
    assert isinstance(data, list) and len(data) == 1
    assert (tmp_path / "params.json").exists()
