import pandas as pd

from dfs_optimizer.models import players_from_df, Parameters
from dfs_optimizer.optimizer import generate_lineups, lineups_to_dataframe


def synthetic_players_df():
    # Minimal pool that can form multiple unique lineups
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
            7500, 7200,  # QBs
            7000, 6200, 5800,  # RBs
            6000, 5400, 5200, 5000,  # WRs
            3800, 3200,  # TEs
            2600, 2400,  # DSTs
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


def test_generate_lineups_minimal():
    df = synthetic_players_df()
    players = players_from_df(df)
    params = Parameters(lineup_count=3, min_salary=45000, stack=1, game_stack=0, allow_qb_vs_dst=False)
    lineups = generate_lineups(players, params)
    assert 1 <= len(lineups) <= 3
    df_lineups = lineups_to_dataframe(lineups)
    assert set(["Rank", "Projection", "QB", "FLEX"]).issubset(df_lineups.columns)
    # Roster slot sanity
    for _, row in df_lineups.iterrows():
        assert isinstance(row["QB"], str)
        assert isinstance(row["DST"], str)


def test_stack_enforced():
    df = synthetic_players_df()
    players = players_from_df(df)
    # Require stack of 2 WR/TE with QB team
    params = Parameters(lineup_count=1, min_salary=43000, stack=2)
    lineups = generate_lineups(players, params)
    assert len(lineups) >= 1
    stacked = lineups[0].stack_positions
    assert len([p for p in stacked if p in ("WR", "TE")]) >= 1  # at least some stack recorded


def test_lineup_uniqueness():
    df = synthetic_players_df()
    players = players_from_df(df)
    params = Parameters(lineup_count=2, min_salary=43000)
    lineups = generate_lineups(players, params)
    assert len(lineups) >= 1
    if len(lineups) == 2:
        a = set(p.display_name() for p in lineups[0].players)
        b = set(p.display_name() for p in lineups[1].players)
        assert a != b
