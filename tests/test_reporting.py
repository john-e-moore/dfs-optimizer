import os
import pandas as pd

from dfs_optimizer.models import Parameters
from dfs_optimizer.reporting import build_parameters_df
from dfs_optimizer.io_utils import write_excel_with_tabs


def test_build_parameters_df_keys_and_values():
    params = Parameters(lineup_count=10, min_salary=44000, allow_qb_vs_dst=True, stack=2, game_stack=3,
                        min_player_projection=5.0, min_sum_ownership=0.9, max_sum_ownership=1.3,
                        min_product_ownership=1e-9, max_product_ownership=0.1)
    df = build_parameters_df(params)
    assert df.loc[0, 'lineup_count'] == 10
    assert 'max_product_ownership' in df.columns


def test_write_excel_tabs(tmp_path):
    projections = pd.DataFrame({"Name": ["A"], "Team": ["X"]})
    params_df = pd.DataFrame({"param": [1]})
    lineups = pd.DataFrame({"Rank": [1], "Projection": [10.5]})
    path = tmp_path / "out.xlsx"
    write_excel_with_tabs(projections, params_df, lineups, str(path))
    assert path.exists()
