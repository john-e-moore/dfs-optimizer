import os
import pandas as pd

from dfs_optimizer.models import Parameters
from dfs_optimizer.reporting import build_parameters_df, build_players_exposure_df
from dfs_optimizer.io_utils import write_excel_with_tabs


def test_build_parameters_df_keys_and_values():
    params = Parameters(lineup_count=10, min_salary=44000, allow_qb_vs_dst=True, stack=2, game_stack=3,
                        min_player_projection=5.0, min_sum_ownership=0.9, max_sum_ownership=1.3,
                        min_product_ownership=1e-9, max_product_ownership=0.1)
    df = build_parameters_df(params)
    assert df.loc[0, 'lineup_count'] == 10
    assert 'max_product_ownership' in df.columns


def test_build_players_exposure_df():
    lineups = pd.DataFrame({
        'Rank': [1, 2, 3],
        'QB': ['A (X)', 'B (Y)', 'A (X)'],
        'RB1': ['R1', 'R2', 'R1'],
        'RB2': ['R3', 'R3', 'R3'],
        'WR1': ['W1', 'W1', 'W2'],
        'WR2': ['W2', 'W2', 'W3'],
        'WR3': ['W3', 'W4', 'W4'],
        'TE': ['T1', 'T2', 'T1'],
        'FLEX': ['F1', 'F1', 'F2'],
        'DST': ['D1', 'D1', 'D2'],
    })
    players_df = build_players_exposure_df(lineups)
    assert set(players_df.columns) == {"Player", "# Lineups", "% Lineups"}
    # A (X) appears twice out of 3 (rounded percent)
    row = players_df[players_df['Player'] == 'A (X)'].iloc[0]
    assert row['# Lineups'] == 2
    assert row['% Lineups'] in (67, 66)


def test_write_excel_tabs_includes_players(tmp_path):
    projections = pd.DataFrame({"Name": ["A"], "Team": ["X"]})
    params_df = pd.DataFrame({"param": [1]})
    lineups = pd.DataFrame({"Rank": [1], "Projection": [10.5], "QB": ["A (X)"], "RB1": ["R1"], "RB2": ["R2"], "WR1": ["W1"], "WR2": ["W2"], "WR3": ["W3"], "TE": ["T1"], "FLEX": ["F1"], "DST": ["D1"]})
    players_df = build_players_exposure_df(lineups)
    path = tmp_path / "out.xlsx"
    write_excel_with_tabs(projections, params_df, lineups, str(path), players_df=players_df)
    assert path.exists()
