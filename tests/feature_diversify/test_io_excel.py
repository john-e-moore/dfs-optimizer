from __future__ import annotations

import os
import tempfile

import pandas as pd

from src.feature_diversify.io_excel import SourceKey, read_lineups_from_source


def test_read_lineups_from_source_roster_columns(tmp_path):
    df = pd.DataFrame(
        [
            {
                "Projection": 120.5,
                "QB": "Josh Allen (BUF)",
                "RB1": "Christian McCaffrey (SF)",
                "RB2": "James Cook (BUF)",
                "WR1": "Stefon Diggs (BUF)",
                "WR2": "Amon-Ra St. Brown (DET)",
                "WR3": "CeeDee Lamb (DAL)",
                "TE": "Dalton Kincaid (BUF)",
                "FLEX": "Tyreek Hill (MIA)",
                "DST": "Bills (BUF)",
            }
        ]
    )
    path = os.path.join(tmp_path, "lineups.xlsx")
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Lineups", index=False)

    src = SourceKey(path=path, sheet="Lineups")
    recs = read_lineups_from_source(src)
    assert len(recs) == 1
    # Ensure we extracted a 9-player set
    assert len(next(iter(recs)).player_tokens) >= 7


