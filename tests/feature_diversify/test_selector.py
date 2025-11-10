from __future__ import annotations

from src.feature_diversify.selector import jaccard_distance, farthest_first_with_quotas
from src.feature_diversify.io_excel import LineupRecord


def make_rec(source: str, idx: int, players: list[str], proj: float | None = None) -> LineupRecord:
    import pandas as pd
    return LineupRecord(
        source_key=source,
        row_index=idx,
        projection=proj,
        player_tokens=set(players),
        original_row=pd.Series({}),
    )


def test_jaccard_distance_basic():
    a = {"A", "B", "C"}
    b = {"A", "B", "D"}
    d = jaccard_distance(a, b)
    # Intersection=2, Union=4 -> 1 - 2/4 = 0.5
    assert abs(d - 0.5) < 1e-9


def test_farthest_first_with_quotas_respects_sources():
    # Two sources, pick 1 from each, ensure global diversification
    recs = [
        make_rec("A:Lineups", 0, ["P1", "P2", "P3"]) ,
        make_rec("A:Lineups", 1, ["P1", "P2", "P4"]) ,
        make_rec("B:Lineups", 2, ["P5", "P6", "P7"]) ,
        make_rec("B:Lineups", 3, ["P5", "P6", "P8"]) ,
    ]
    quotas = {"A:Lineups": 1, "B:Lineups": 1}
    result = farthest_first_with_quotas(recs, quotas, seed=0)
    assert len(result.selected) == 2
    # Selected should include one from each source
    sources = {r.source_key for r in result.selected}
    assert sources == set(quotas.keys())


