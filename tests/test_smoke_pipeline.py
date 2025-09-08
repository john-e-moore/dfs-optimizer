import re
import numpy as np
import pandas as pd

from dfs_optimizer.models import players_from_df, Parameters
from dfs_optimizer.optimizer import generate_lineups, lineups_to_dataframe
from dfs_optimizer.filters import filter_lineups


def synthetic_pool_df():
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


def test_end_to_end_smoke():
    df = synthetic_pool_df()
    players = players_from_df(df)
    params = Parameters(lineup_count=3, min_salary=43000, stack=1, game_stack=0)

    lineups = generate_lineups(players, params, max_lineups=3)
    assert 1 <= len(lineups) <= 3

    # Apply a permissive filter to keep all
    fr = filter_lineups(lineups, Parameters())
    kept = fr.lineups
    assert len(kept) == len(lineups)

    out = lineups_to_dataframe(kept)
    # Required columns
    for c in ["Rank", "Projection", "Sum Ownership", "Product Ownership", "# Stacked", "QB Stack", "RB/DST Stack", "Game Stack", "QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]:
        assert c in out.columns

    # Sum Ownership should be integer percent (accept numpy integer types)
    assert isinstance(out.loc[0, "Sum Ownership"], (int, np.integer))

    # Game Stack formatting: TEAM/TEAM (N)
    assert re.match(r"^[A-Z]{1,3}/[A-Z]{1,3} \(\d+\)$", out.loc[0, "Game Stack"]) is not None

    # Uniqueness of players within a lineup row
    for _, row in out.iterrows():
        names = [row[c] for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]]
        assert len(names) == len(set(names))
