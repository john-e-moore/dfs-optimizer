import pandas as pd
import pytest

from dfs_optimizer.models import Player, Parameters, game_key, players_from_df


def test_game_key_ordering():
    assert game_key("KC", "DEN") == "DEN-KC"
    assert game_key("den", "kc") == "DEN-KC"


def test_parameters_validation():
    p = Parameters()
    p.validate()  # should not raise
    p2 = Parameters(min_salary=60000)
    with pytest.raises(AssertionError):
        p2.validate()


def test_players_from_df_and_display():
    df = pd.DataFrame(
        {
            "Name": ["P1", "P2"],
            "Team": ["KC", "DEN"],
            "Opponent": ["DEN", "KC"],
            "Position": ["QB", "WR"],
            "Salary": [8000, 6000],
            "Projection": [25.0, 15.0],
            "Ownership": [0.12, 0.08],
        }
    )
    players = players_from_df(df)
    assert len(players) == 2
    assert isinstance(players[0], Player)
    assert players[0].display_name().endswith("(KC)")


def test_players_from_df_ownership_fraction_required():
    df = pd.DataFrame(
        {
            "Name": ["P"],
            "Team": ["KC"],
            "Opponent": ["DEN"],
            "Position": ["QB"],
            "Salary": [8000],
            "Projection": [25.0],
            "Ownership": [12.0],  # not normalized, should fail here
        }
    )
    with pytest.raises(AssertionError):
        players_from_df(df)
