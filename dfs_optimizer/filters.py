from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import Parameters
from .optimizer import LineupResult


@dataclass
class FilterResult:
    lineups: List[LineupResult]
    dropped: int


def _passes_min_player_projection(lineup: LineupResult, threshold: float) -> bool:
    return all(p.projection >= threshold for p in lineup.players)


def _passes_sum_ownership(lineup: LineupResult, min_sum: Optional[float], max_sum: Optional[float]) -> bool:
    v = lineup.sum_ownership
    if min_sum is not None and v < min_sum:
        return False
    if max_sum is not None and v > max_sum:
        return False
    return True


def _passes_product_ownership(lineup: LineupResult, min_prod: Optional[float], max_prod: Optional[float]) -> bool:
    v = lineup.product_ownership
    if min_prod is not None and v < min_prod:
        return False
    if max_prod is not None and v > max_prod:
        return False
    return True


def filter_lineups(lineups: List[LineupResult], params: Parameters) -> FilterResult:
    if not any(
        [
            params.min_player_projection is not None,
            params.min_sum_ownership is not None,
            params.max_sum_ownership is not None,
            params.min_product_ownership is not None,
            params.max_product_ownership is not None,
        ]
    ):
        return FilterResult(lineups=list(lineups), dropped=0)

    kept: List[LineupResult] = []
    for lu in lineups:
        if params.min_player_projection is not None and not _passes_min_player_projection(
            lu, params.min_player_projection
        ):
            continue
        if not _passes_sum_ownership(lu, params.min_sum_ownership, params.max_sum_ownership):
            continue
        if not _passes_product_ownership(
            lu, params.min_product_ownership, params.max_product_ownership
        ):
            continue
        kept.append(lu)
    return FilterResult(lineups=kept, dropped=len(lineups) - len(kept))
