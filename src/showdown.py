from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, List, Tuple

import pandas as pd
import pulp

from .logging_utils import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class ShowdownEntry:
    name: str
    team: str
    opponent: str
    position: str
    role: str  # "CPT" or "FLEX"
    salary: int
    projection: float
    ownership: float


@dataclass(frozen=True)
class ShowdownLineupResult:
    entries: Tuple[ShowdownEntry, ...]
    total_projection: float
    total_salary: int
    sum_ownership: float
    product_ownership: float
    weighted_ownership: float

    def to_row(self, start_time_map: Dict[Tuple[str, str], int] | None = None) -> Dict[str, object]:
        row: Dict[str, object] = {}
        row["Projection"] = self.total_projection
        row["Salary"] = int(self.total_salary)
        row["Sum Ownership"] = int(round(self.sum_ownership * 100))
        row["Product Ownership"] = int(self.product_ownership * 1_000_000_000)
        row["Weighted Ownership"] = round(self.weighted_ownership * 100, 1)
        # Split CPT vs FLEX and order FLEX deterministically by (start time, projection)
        cpt = next(e for e in self.entries if e.role == "CPT")
        flex_entries = [e for e in self.entries if e.role != "CPT"]

        def _start_time(entry: ShowdownEntry) -> int:
            if not start_time_map:
                return 0
            key = (entry.name.upper().strip(), entry.team.upper().strip())
            return int(start_time_map.get(key, 0))

        # Order by later start first, tie-break by projection desc
        flex_sorted = sorted(flex_entries, key=lambda e: (_start_time(e), e.projection), reverse=True)

        def fmt(e: ShowdownEntry) -> str:
            return f"{e.name} ({e.ownership * 100:.1f}%)"

        row["CPT"] = fmt(cpt)
        for i, e in enumerate(flex_sorted[:5], start=1):
            row[f"FLEX{i}"] = fmt(e)
        # Ensure all FLEX columns exist
        for i in range(1, 6):
            col = f"FLEX{i}"
            if col not in row:
                row[col] = None
        return row


def entries_from_df(df: pd.DataFrame) -> List[ShowdownEntry]:
    required = ["Name", "Team", "Opponent", "Position", "Salary", "Projection", "Ownership", "ShowdownRole"]
    missing = [c for c in required if c not in df.columns]
    assert not missing, f"Missing columns for showdown entries: {missing}"
    entries: List[ShowdownEntry] = []
    for _, r in df.iterrows():
        try:
            name = str(r["Name"])
            team = str(r["Team"]).upper()
            opp = str(r["Opponent"]).upper()
            pos = str(r["Position"]).upper()
            role = str(r["ShowdownRole"]).upper()
            salary = int(r["Salary"])
            proj = float(r["Projection"])
            own = float(r["Ownership"])
        except Exception as e:
            raise AssertionError(f"Invalid row for showdown: {e}")
        entries.append(
            ShowdownEntry(
                name=name,
                team=team,
                opponent=opp,
                position=pos,
                role=role,
                salary=salary,
                projection=proj,
                ownership=own,
            )
        )
    return entries


def generate_lineups_showdown(entries: List[ShowdownEntry], params, max_lineups: int | None = None) -> List[ShowdownLineupResult]:
    target = max_lineups or params.lineup_count
    index = list(range(len(entries)))
    cpt_idxs = [i for i, e in enumerate(entries) if e.role == "CPT"]
    flex_idxs = [i for i, e in enumerate(entries) if e.role != "CPT"]
    # Base identity to avoid selecting both CPT and FLEX of same player
    base_key = lambda e: f"{e.name}|{e.team}"
    base_to_idxs: Dict[str, List[int]] = {}
    team_to_idxs: Dict[str, List[int]] = {}
    name_to_idxs: Dict[str, List[int]] = {}
    for i, e in enumerate(entries):
        base_to_idxs.setdefault(base_key(e), []).append(i)
        team_to_idxs.setdefault(e.team, []).append(i)
        name_to_idxs.setdefault(e.name, []).append(i)

    lineups: List[ShowdownLineupResult] = []
    previous_solutions: List[List[int]] = []

    # CBC solver configuration reused
    effective_threads = params.solver_threads if params.solver_threads is not None else (os.cpu_count() or 1)
    effective_time_limit = float(params.solver_time_limit_s) if params.solver_time_limit_s is not None else None
    solver_kwargs: Dict[str, object] = {"msg": False, "threads": int(effective_threads)}
    if effective_time_limit is not None:
        solver_kwargs["timeLimit"] = effective_time_limit
    solver_cmd = pulp.PULP_CBC_CMD(**solver_kwargs)
    logger.info("Showdown solver settings: CBC threads=%d timeLimit=%s", int(effective_threads), str(effective_time_limit))

    # Build MILP model once and iterate with uniqueness cuts
    prob = pulp.LpProblem("DFS_Showdown_Optimizer", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("x", index, lowBound=0, upBound=1, cat="Binary")

    # Objective: maximize projection
    prob += pulp.lpSum(entries[i].projection * x[i] for i in index)

    # Roster size and role counts
    prob += pulp.lpSum(x[i] for i in index) == 6
    prob += pulp.lpSum(x[i] for i in cpt_idxs) == 1
    prob += pulp.lpSum(x[i] for i in flex_idxs) == 5

    # Salary bounds
    prob += pulp.lpSum(entries[i].salary * x[i] for i in index) <= 50000
    prob += pulp.lpSum(entries[i].salary * x[i] for i in index) >= params.min_salary

    # Cannot select both CPT and FLEX of same player (by Name+Team)
    for key, idxs in base_to_idxs.items():
        if len(idxs) > 1:
            prob += pulp.lpSum(x[i] for i in idxs) <= 1

    # Projection sum bounds
    if getattr(params, "min_sum_projection", None) is not None:
        prob += pulp.lpSum(entries[i].projection * x[i] for i in index) >= float(params.min_sum_projection)
    if getattr(params, "max_sum_projection", None) is not None:
        prob += pulp.lpSum(entries[i].projection * x[i] for i in index) <= float(params.max_sum_projection)

    # Ownership bounds
    if getattr(params, "min_sum_ownership", None) is not None:
        prob += pulp.lpSum(entries[i].ownership * x[i] for i in index) >= float(params.min_sum_ownership)
    if getattr(params, "max_sum_ownership", None) is not None:
        prob += pulp.lpSum(entries[i].ownership * x[i] for i in index) <= float(params.max_sum_ownership)

    # Ownership product bounds via log transform
    import math

    eps = 1e-6
    log_ownership = {i: math.log(max(entries[i].ownership, eps)) for i in index}
    if getattr(params, "min_product_ownership", None) is not None:
        prob += pulp.lpSum(log_ownership[i] * x[i] for i in index) >= math.log(max(params.min_product_ownership, eps))
    if getattr(params, "max_product_ownership", None) is not None:
        prob += pulp.lpSum(log_ownership[i] * x[i] for i in index) <= math.log(max(params.max_product_ownership, eps))

    # Weighted ownership
    weighted_coeff = {i: (entries[i].salary / 50000.0) * entries[i].ownership for i in index}
    if getattr(params, "min_weighted_ownership", None) is not None:
        prob += pulp.lpSum(weighted_coeff[i] * x[i] for i in index) >= float(params.min_weighted_ownership)
    if getattr(params, "max_weighted_ownership", None) is not None:
        prob += pulp.lpSum(weighted_coeff[i] * x[i] for i in index) <= float(params.max_weighted_ownership)

    # Exclusions by player name
    if getattr(params, "excluded_players", None):
        for name in params.excluded_players:
            for i in name_to_idxs.get(name, []):
                prob += x[i] == 0
    # Exclusions by team
    if getattr(params, "excluded_teams", None):
        for t in params.excluded_teams:
            for i in team_to_idxs.get(t, []):
                prob += x[i] == 0
    # Required players by name (either CPT or FLEX variant)
    if getattr(params, "included_players", None):
        for name in params.included_players:
            idxs = name_to_idxs.get(name, [])
            assert idxs, f"Included player not in pool: {name}"
            prob += pulp.lpSum(x[i] for i in idxs) >= 1
    # Minimum players by team
    if getattr(params, "min_players_by_team", None):
        for t, m in params.min_players_by_team.items():
            idxs = team_to_idxs.get(t, [])
            if idxs:
                prob += pulp.lpSum(x[i] for i in idxs) >= int(m)

    while len(lineups) < target:
        status = prob.solve(solver_cmd)
        if status != pulp.LpStatusOptimal:
            logger.info("No more optimal showdown solutions found (status=%s)", pulp.LpStatus[status])
            break
        selected_idxs = [i for i in index if x[i].value() == 1]
        assert len(selected_idxs) == 6
        selected = [entries[i] for i in selected_idxs]
        assert sum(1 for e in selected if e.role == "CPT") == 1
        total_salary = sum(e.salary for e in selected)
        assert params.min_salary <= total_salary <= 50000
        total_projection = sum(e.projection for e in selected)
        sum_ownership = sum(e.ownership for e in selected)
        product_ownership = 1.0
        for e in selected:
            product_ownership *= max(e.ownership, 1e-9)
        weighted_ownership = sum((e.salary / 50000.0) * e.ownership for e in selected)
        lineups.append(
            ShowdownLineupResult(
                entries=tuple(selected),
                total_projection=total_projection,
                total_salary=total_salary,
                sum_ownership=sum_ownership,
                product_ownership=product_ownership,
                weighted_ownership=weighted_ownership,
            )
        )
        previous_solutions.append(selected_idxs)
        # Set-based uniqueness (treat FLEX positions as indistinguishable)
        prob += pulp.lpSum(x[i] for i in selected_idxs) <= 5

    return lineups


def lineups_to_dataframe_showdown(lineups: List[ShowdownLineupResult], start_time_map: Dict[Tuple[str, str], int] | None = None) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for i, lu in enumerate(sorted(lineups, key=lambda l: l.total_projection, reverse=True), start=1):
        row = lu.to_row(start_time_map)
        row["Rank"] = i
        rows.append(row)
    cols = [
        "Rank",
        "Projection",
        "Salary",
        "Sum Ownership",
        "Product Ownership",
        "Weighted Ownership",
        "CPT",
        "FLEX1",
        "FLEX2",
        "FLEX3",
        "FLEX4",
        "FLEX5",
    ]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


