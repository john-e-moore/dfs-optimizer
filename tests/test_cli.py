import os
import tempfile

from src.cli import main


def test_cli_smoke(monkeypatch):
    # Use the real projections path; outputs to temp files
    tmpdir = tempfile.mkdtemp()
    code = main([
        "--lineups", "5",
        "--min-salary", "45000",
        "--stack", "1",
        "--out-unfiltered", os.path.join(tmpdir, "u.xlsx"),
        "--out-filtered", os.path.join(tmpdir, "f.xlsx"),
    ])
    assert code == 0
    assert os.path.exists(os.path.join(tmpdir, "u.xlsx"))
    assert os.path.exists(os.path.join(tmpdir, "f.xlsx"))
