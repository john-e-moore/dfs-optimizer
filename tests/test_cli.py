import os
import tempfile

from src.cli import main


def test_cli_smoke_outputs_under_outdir(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    code = main([
        "--lineups", "3",
        "--min-salary", "45000",
        "--stack", "1",
        "--outdir", tmpdir,
    ])
    assert code == 0
    # Expect a timestamped subdirectory containing lineups.xlsx and lineups.json
    entries = os.listdir(tmpdir)
    assert len(entries) == 1
    run_dir = os.path.join(tmpdir, entries[0])
    assert os.path.isdir(run_dir)
    assert os.path.exists(os.path.join(run_dir, "lineups.xlsx"))
    assert os.path.exists(os.path.join(run_dir, "lineups.json"))
