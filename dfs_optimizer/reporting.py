from __future__ import annotations

import dataclasses
from typing import Any, Dict

import pandas as pd

from .models import Parameters
from .io_utils import write_excel_with_tabs


def build_parameters_df(params: Parameters) -> pd.DataFrame:
    data: Dict[str, Any] = dataclasses.asdict(params)
    # Keep order stable for readability
    ordered_keys = [
        "lineup_count",
        "min_salary",
        "allow_qb_vs_dst",
        "stack",
        "game_stack",
        "min_player_projection",
        "min_sum_ownership",
        "max_sum_ownership",
        "min_product_ownership",
        "max_product_ownership",
        "solver_threads",
        "solver_time_limit_s",
    ]
    row = {k: data.get(k) for k in ordered_keys}
    return pd.DataFrame([row])


def export_workbook(projections_df: pd.DataFrame, params: Parameters, lineups_df: pd.DataFrame, path: str) -> None:
    params_df = build_parameters_df(params)
    write_excel_with_tabs(projections_df, params_df, lineups_df, path)
