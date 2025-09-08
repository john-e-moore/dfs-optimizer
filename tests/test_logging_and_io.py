import os
import pandas as pd

from dfs_optimizer.logging_utils import setup_logger
from dfs_optimizer.io_utils import ensure_dir, write_csv, read_csv, write_excel_with_tabs


def test_setup_logger_idempotent():
    logger1 = setup_logger("test")
    logger2 = setup_logger("test")
    assert logger1 is logger2


def test_csv_roundtrip(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    path = tmp_path / "out.csv"
    write_csv(df, str(path))
    assert path.exists()
    df2 = read_csv(str(path))
    assert df2.equals(df)


def test_write_excel_with_tabs(tmp_path):
    projections = pd.DataFrame({"Name": ["A"], "Team": ["X"]})
    params = pd.DataFrame({"param": [1]})
    lineups = pd.DataFrame({"Rank": [1], "Projection": [10.5]})
    xls_path = tmp_path / "book.xlsx"
    write_excel_with_tabs(projections, params, lineups, str(xls_path))
    assert xls_path.exists()
