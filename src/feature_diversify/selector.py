from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import math
import random

from .io_excel import LineupRecord


def jaccard_distance(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return 1.0 - (inter / union)


def _avg_distance_to_pool(target: Set[str], pool: Sequence[Set[str]]) -> float:
    if not pool:
        return 0.0
    s = 0.0
    for other in pool:
        s += jaccard_distance(target, other)
    return s / float(len(pool))


@dataclass
class SelectionResult:
    selected: List[LineupRecord]
    min_pairwise_jaccard: float
    avg_pairwise_jaccard: float


def farthest_first_with_quotas(
    candidates: List[LineupRecord],
    quotas_by_source: Dict[str, int],
    *,
    seed: Optional[int] = None,
) -> SelectionResult:
    # Filter out sources not in quotas
    sources_allowed = set(quotas_by_source.keys())
    pool = [c for c in candidates if c.source_key in sources_allowed]
    if not pool:
        return SelectionResult([], float("nan"), float("nan"))

    rng = random.Random(seed)

    # Precompute sets for speed
    sets: List[Set[str]] = [c.player_tokens for c in pool]

    # Seed selection: highest avg distance to the pool (fallback to highest projection)
    best_idx = -1
    best_score = -1.0
    for i, s in enumerate(sets):
        score = _avg_distance_to_pool(s, sets[:i] + sets[i + 1 :])
        if score > best_score:
            best_score = score
            best_idx = i
    if best_idx < 0:
        # Fallback: choose by highest projection
        best_idx = max(range(len(pool)), key=lambda i: (pool[i].projection or float("-inf"), -pool[i].row_index))

    selected: List[LineupRecord] = []
    selected_sets: List[Set[str]] = []
    remaining_by_source: Dict[str, int] = dict(quotas_by_source)

    def can_take_from(source_key: str) -> bool:
        return remaining_by_source.get(source_key, 0) > 0

    # Take the seed if its source has quota
    if can_take_from(pool[best_idx].source_key):
        selected.append(pool[best_idx])
        selected_sets.append(sets[best_idx])
        remaining_by_source[pool[best_idx].source_key] -= 1

    # Build candidate indices not yet chosen
    remaining_indices = [i for i in range(len(pool)) if i != best_idx]

    # Greedy iterations
    while any(v > 0 for v in remaining_by_source.values()):
        best_i = -1
        best_min_dist = -1.0
        best_tiebreak = (float("-inf"), float("inf"))  # (projection, row_index negative)

        for i in remaining_indices:
            rec = pool[i]
            if not can_take_from(rec.source_key):
                continue
            s = sets[i]
            if selected_sets:
                min_dist = min(jaccard_distance(s, t) for t in selected_sets)
            else:
                min_dist = _avg_distance_to_pool(s, sets[:i] + sets[i + 1 :])

            proj = rec.projection if rec.projection is not None else float("-inf")
            tiebreak = (proj, -rec.row_index)
            if (min_dist > best_min_dist) or (
                math.isclose(min_dist, best_min_dist) and tiebreak > best_tiebreak
            ):
                best_min_dist = min_dist
                best_tiebreak = tiebreak
                best_i = i

        if best_i < 0:
            # No feasible candidate for remaining quotas
            break

        # Take the chosen candidate
        selected.append(pool[best_i])
        selected_sets.append(sets[best_i])
        remaining_by_source[pool[best_i].source_key] -= 1
        # Remove from remaining indices
        remaining_indices = [i for i in remaining_indices if i != best_i]

    # Compute metrics
    if len(selected_sets) >= 2:
        dists: List[float] = []
        for i in range(len(selected_sets)):
            for j in range(i + 1, len(selected_sets)):
                dists.append(jaccard_distance(selected_sets[i], selected_sets[j]))
        min_j = min(dists) if dists else float("nan")
        avg_j = sum(dists) / len(dists) if dists else float("nan")
    else:
        min_j = float("nan")
        avg_j = float("nan")

    return SelectionResult(selected=selected, min_pairwise_jaccard=min_j, avg_pairwise_jaccard=avg_j)


