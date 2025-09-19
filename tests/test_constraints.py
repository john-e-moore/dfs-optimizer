import json
import os
import tempfile

import pandas as pd

from src.models import players_from_df, Parameters
from src.optimizer import generate_lineups
from src.cli import main


def synthetic_players_df():
    data = {
        "Name": [
            "QB1", "QB2",
            "RB1", "RB2", "RB3",
            "WR1", "WR2", "WR3", "WR4",
            "TE1", "TE2",
            "DST1", "DST2",
        ],
        "Team": [
            "A", "B",
            "A", "A", "B",
            "A", "A", "B", "B",
            "A", "B",
            "A", "B",
        ],
        "Opponent": [
            "B", "A",
            "B", "B", "A",
            "B", "B", "A", "A",
            "B", "A",
            "B", "A",
        ],
        "Position": [
            "QB", "QB",
            "RB", "RB", "RB",
            "WR", "WR", "WR", "WR",
            "TE", "TE",
            "DST", "DST",
        ],
        "Salary": [
            7500, 7200,
            7000, 6200, 5800,
            6000, 5400, 5200, 5000,
            3800, 3200,
            2600, 2400,
        ],
        "Projection": [
            22.0, 21.0,
            18.0, 17.0, 15.0,
            16.0, 15.5, 14.5, 14.0,
            12.0, 11.5,
            8.0, 7.5,
        ],
        "Ownership": [0.15, 0.14, 0.2, 0.18, 0.12, 0.18, 0.16, 0.12, 0.11, 0.09, 0.08, 0.05, 0.04],
    }
    return pd.DataFrame(data)


def test_min_sum_projection_infeasible():
    df = synthetic_players_df()
    players = players_from_df(df)
    params = Parameters(lineup_count=1, min_salary=43000, min_sum_projection=500.0)
    lineups = generate_lineups(players, params)
    assert len(lineups) == 0


def test_sum_ownership_bounds_enforced():
    df = synthetic_players_df()
    players = players_from_df(df)
    params = Parameters(lineup_count=1, min_salary=43000, min_sum_ownership=0.9, max_sum_ownership=2.0)
    lineups = generate_lineups(players, params)
    assert len(lineups) <= 1
    for lu in lineups:
        assert 0.9 <= lu.sum_ownership <= 2.0


def test_product_ownership_min_infeasible():
    df = synthetic_players_df()
    players = players_from_df(df)
    params = Parameters(lineup_count=1, min_salary=43000, min_product_ownership=0.5)
    lineups = generate_lineups(players, params)
    assert len(lineups) == 0


def test_cli_infeasible_writes_outputs():
    tmpdir = tempfile.mkdtemp()
    code = main([
        "--lineups", "1",
        "--min-salary", "43000",
        "--min-sum-projection", "500",
        "--outdir", tmpdir,
    ])
    assert code == 0
    entries = os.listdir(tmpdir)
    assert len(entries) == 1
    run_dir = os.path.join(tmpdir, entries[0])
    with open(os.path.join(run_dir, "lineups.json"), "r", encoding="utf-8") as f:
        payload = json.load(f)
    assert isinstance(payload, list)
    assert len(payload) == 0
    assert os.path.exists(os.path.join(run_dir, "lineups.xlsx"))


