from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, List, Tuple

import pandas as pd
import pulp

from .models import Player, Parameters, game_key
from .logging_utils import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class LineupResult:
    players: Tuple[Player, ...]
    total_projection: float
    total_salary: int
    sum_ownership: float
    product_ownership: float
    weighted_ownership: float
    stack_positions: Tuple[str, ...]
    max_game_stack: int
    max_game_key: str
    stack_count: int
    all_game_stacks: Tuple[Tuple[str, int], ...]
    rb_dst_stack: bool

    def to_row(self) -> Dict[str, object]:
        row: Dict[str, object] = {}
        row["Projection"] = self.total_projection
        row["Salary"] = int(self.total_salary)
        # Display sum ownership as integer percentage (e.g., 1.56 -> 156)
        row["Sum Ownership"] = int(round(self.sum_ownership * 100))
        row["Product Ownership"] = int(self.product_ownership * 1_000_000_000)
        # Display weighted ownership as integer percent: sum((salary/50000)*ownership) * 100
        row["Weighted Ownership"] = int(round(self.weighted_ownership * 100))
        row["# Stacked"] = int(self.stack_count)
        row["QB Stack"] = ",".join(self.stack_positions)
        row["RB/DST Stack"] = bool(self.rb_dst_stack)
        # Build multi-game stack string like "CIN/CLE (4), ATL/TB (2)"
        parts = [f"{k.replace('-', '/')} ({v})" for k, v in self.all_game_stacks if v > 1]
        row["Game Stack"] = ", ".join(parts)
        # Ordered player slots: QB, RB, RB, WR, WR, WR, TE, FLEX, DST
        players_by_pos = sorted(self.players, key=lambda p: (pos_order(p.position), -p.projection))
        # Build slots by consuming required counts
        slots: List[Player] = [None] * 9  # type: ignore
        # Assign exact counts
        qb = [p for p in players_by_pos if p.position == "QB"]
        dst = [p for p in players_by_pos if p.position == "DST"]
        rb = [p for p in players_by_pos if p.position == "RB"]
        wr = [p for p in players_by_pos if p.position == "WR"]
        te = [p for p in players_by_pos if p.position == "TE"]
        flex_candidates = [p for p in players_by_pos if p.position in {"RB", "WR", "TE"}]
        assert len(qb) == 1 and len(dst) == 1 and len(rb) >= 2 and len(wr) >= 3 and len(te) >= 1
        slots[0] = qb[0]
        slots[1] = rb[0]
        slots[2] = rb[1]
        slots[3] = wr[0]
        slots[4] = wr[1]
        slots[5] = wr[2]
        slots[6] = te[0]
        # FLEX is any remaining highest projection among candidates not already used in slots 1..6
        used_ids = {id(x) for x in slots[:7]}
        flex = next(p for p in flex_candidates if id(p) not in used_ids)
        slots[7] = flex
        slots[8] = dst[0]
        # Fill columns with Name (OWNERSHIP%) where ownership is shown as a percentage with one decimal
        def fmt(p: Player) -> str:
            return f"{p.name} ({p.ownership * 100:.1f}%)"
        name_cols = [
            fmt(slots[0]),
            fmt(slots[1]),
            fmt(slots[2]),
            fmt(slots[3]),
            fmt(slots[4]),
            fmt(slots[5]),
            fmt(slots[6]),
            fmt(slots[7]),
            fmt(slots[8]),
        ]
        # Attach player names in order after metadata columns
        row.update(
            {
                "QB": name_cols[0],
                "RB1": name_cols[1],
                "RB2": name_cols[2],
                "WR1": name_cols[3],
                "WR2": name_cols[4],
                "WR3": name_cols[5],
                "TE": name_cols[6],
                "FLEX": name_cols[7],
                "DST": name_cols[8],
            }
        )
        return row


def pos_order(pos: str) -> int:
    order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "DST": 4}
    return order.get(pos, 9)


def compute_stack_positions(players: List[Player]) -> Tuple[Tuple[str, ...], int, str, int, Tuple[Tuple[str, int], ...], bool]:
    qb_players = [p for p in players if p.position == "QB"]
    assert len(qb_players) == 1
    qb_team = qb_players[0].team
    # Unique positions for display
    stacked = sorted({p.position for p in players if p.team == qb_team and p.position in {"WR", "TE"}})
    # Count of WR/TE stacked (not deduplicated)
    stack_count = sum(1 for p in players if p.team == qb_team and p.position in {"WR", "TE"})
    # Compute max players from same game (exclude DST)
    game_counts: Dict[str, int] = {}
    for p in players:
        if p.position == "DST":
            continue
        g = game_key(p.team, p.opponent)
        game_counts[g] = game_counts.get(g, 0) + 1
    if game_counts:
        max_game_key = max(game_counts, key=lambda k: game_counts[k])
        max_game = game_counts[max_game_key]
    else:
        max_game_key = ""
        max_game = 0
    # Sort all games by count desc then key asc
    all_games_sorted = tuple(sorted(game_counts.items(), key=lambda kv: (-kv[1], kv[0])))
    # RB/DST stack: any RB matching the DST team
    dst_team = next((p.team for p in players if p.position == "DST"), None)
    rb_dst = any((p.position == "RB" and p.team == dst_team) for p in players) if dst_team else False
    return tuple(stacked), max_game, max_game_key, stack_count, all_games_sorted, rb_dst


def generate_lineups(players: List[Player], params: Parameters, max_lineups: int | None = None) -> List[LineupResult]:
    params.validate()
    target_lineups = max_lineups or params.lineup_count

    # Preindex players by position and attributes
    index = list(range(len(players)))
    pos_idxs = {
        "QB": [i for i, p in enumerate(players) if p.position == "QB"],
        "RB": [i for i, p in enumerate(players) if p.position == "RB"],
        "WR": [i for i, p in enumerate(players) if p.position == "WR"],
        "TE": [i for i, p in enumerate(players) if p.position == "TE"],
        "DST": [i for i, p in enumerate(players) if p.position == "DST"],
    }

    # Precompute sets
    team_to_qb_idxs: Dict[str, List[int]] = {}
    team_to_wrte_idxs: Dict[str, List[int]] = {}
    team_to_rb_idxs: Dict[str, List[int]] = {}
    team_to_all_idxs: Dict[str, List[int]] = {}
    game_to_idxs: Dict[str, List[int]] = {}
    dst_opp_to_idxs: Dict[str, List[int]] = {}
    name_to_idxs: Dict[str, List[int]] = {}

    for i, p in enumerate(players):
        if p.position == "QB":
            team_to_qb_idxs.setdefault(p.team, []).append(i)
        if p.position in {"WR", "TE"}:
            team_to_wrte_idxs.setdefault(p.team, []).append(i)
        if p.position == "RB":
            team_to_rb_idxs.setdefault(p.team, []).append(i)
        team_to_all_idxs.setdefault(p.team, []).append(i)
        if p.position == "DST":
            dst_opp_to_idxs.setdefault(p.opponent, []).append(i)
        # Exclude DST from game stack constraints
        if p.position != "DST":
            game_to_idxs.setdefault(game_key(p.team, p.opponent), []).append(i)
        name_to_idxs.setdefault(p.name, []).append(i)

    lineups: List[LineupResult] = []
    previous_solutions: List[List[int]] = []

    # Configure CBC solver (threads/time limit) once per run
    effective_threads = params.solver_threads if params.solver_threads is not None else (os.cpu_count() or 1)
    effective_time_limit = float(params.solver_time_limit_s) if params.solver_time_limit_s is not None else None
    solver_kwargs: Dict[str, object] = {"msg": False, "threads": int(effective_threads)}
    if effective_time_limit is not None:
        solver_kwargs["timeLimit"] = effective_time_limit
    solver_cmd = pulp.PULP_CBC_CMD(**solver_kwargs)
    logger.info("Solver settings: CBC threads=%d timeLimit=%s", int(effective_threads), str(effective_time_limit))

    # Build the MILP once
    prob = pulp.LpProblem("DFS_Optimizer", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("x", index, lowBound=0, upBound=1, cat="Binary")

    # Objective: maximize projection
    prob += pulp.lpSum(players[i].projection * x[i] for i in index)

    # Roster size and position counts
    prob += pulp.lpSum(x[i] for i in index) == 9
    prob += pulp.lpSum(x[i] for i in pos_idxs["QB"]) == 1
    prob += pulp.lpSum(x[i] for i in pos_idxs["DST"]) == 1
    prob += pulp.lpSum(x[i] for i in pos_idxs["RB"]) >= 2
    prob += pulp.lpSum(x[i] for i in pos_idxs["WR"]) >= 3
    prob += pulp.lpSum(x[i] for i in pos_idxs["TE"]) >= 1

    # Salary bounds
    prob += pulp.lpSum(players[i].salary * x[i] for i in index) <= 50000
    prob += pulp.lpSum(players[i].salary * x[i] for i in index) >= params.min_salary

    # Exclusions by player name
    if params.excluded_players:
        for name in params.excluded_players:
            for i in name_to_idxs.get(name, []):
                prob += x[i] == 0

    # Exclusions by team
    if params.excluded_teams:
        for t in params.excluded_teams:
            for i in team_to_all_idxs.get(t, []):
                prob += x[i] == 0

    # Required players by name
    if params.included_players:
        for name in params.included_players:
            idxs = name_to_idxs.get(name, [])
            assert idxs, f"Included player not in pool: {name}"
            for i in idxs:
                prob += x[i] == 1

    # Stack with QB: sum WR/TE from QB team >= stack
    if params.stack and params.stack > 0:
        for team, qb_idxs in team_to_qb_idxs.items():
            prob += (
                pulp.lpSum(x[i] for i in team_to_wrte_idxs.get(team, []))
                >= params.stack * pulp.lpSum(x[i] for i in qb_idxs)
            )

    # Game stack: at least one game with >= game_stack players
    z = None
    if params.game_stack and params.game_stack > 0:
        z = pulp.LpVariable.dicts(
            "z_game",
            list(game_to_idxs.keys()),
            lowBound=0,
            upBound=1,
            cat="Binary",
        )
        for g, idxs in game_to_idxs.items():
            prob += pulp.lpSum(x[i] for i in idxs) >= params.game_stack * z[g]
        prob += pulp.lpSum(z[g] for g in game_to_idxs.keys()) >= 1

    # Disallow QB vs opposing DST if configured
    if not params.allow_qb_vs_dst:
        for team, qb_idxs in team_to_qb_idxs.items():
            opp_dst_idxs = dst_opp_to_idxs.get(team, [])
            if opp_dst_idxs:
                prob += (
                    pulp.lpSum(x[i] for i in qb_idxs)
                    + pulp.lpSum(x[i] for i in opp_dst_idxs)
                    <= 1
                )

    # Minimum players by team
    if params.min_players_by_team:
        for t, m in params.min_players_by_team.items():
            idxs = team_to_all_idxs.get(t, [])
            if idxs:
                prob += pulp.lpSum(x[i] for i in idxs) >= int(m)

    # RB/DST stack: if DST from team t is selected, require at least one RB from team t
    if params.rb_dst_stack:
        for t, dst_idxs in team_to_all_idxs.items():
            # Filter DST indices for team t
            dst_idxs_t = [i for i in dst_idxs if players[i].position == "DST"]
            rb_idxs_t = team_to_rb_idxs.get(t, [])
            if not dst_idxs_t:
                continue
            # If a DST exists but no RBs exist for that team, this will make selection of that DST impossible
            for i_dst in dst_idxs_t:
                if rb_idxs_t:
                    prob += x[i_dst] <= pulp.lpSum(x[i] for i in rb_idxs_t)
                else:
                    # No RBs: force DST off to maintain feasibility
                    prob += x[i_dst] == 0

    # Iteratively solve and add uniqueness constraints
    while len(lineups) < target_lineups:
        status = prob.solve(solver_cmd)
        if status != pulp.LpStatusOptimal:
            logger.info("No more optimal solutions found (status=%s)", pulp.LpStatus[status])
            break

        selected_idxs = [i for i in index if x[i].value() == 1]
        assert len(selected_idxs) == 9
        selected_players = [players[i] for i in selected_idxs]

        # Sanity checks
        assert sum(1 for p in selected_players if p.position == "QB") == 1
        assert sum(1 for p in selected_players if p.position == "DST") == 1
        assert sum(1 for p in selected_players if p.position == "RB") >= 2
        assert sum(1 for p in selected_players if p.position == "WR") >= 3
        assert sum(1 for p in selected_players if p.position == "TE") >= 1

        total_salary = sum(p.salary for p in selected_players)
        assert params.min_salary <= total_salary <= 50000

        total_projection = sum(p.projection for p in selected_players)
        sum_ownership = sum(p.ownership for p in selected_players)
        product_ownership = 1.0
        for p in selected_players:
            product_ownership *= max(p.ownership, 1e-9)
        weighted_ownership = sum((p.salary / 50000.0) * p.ownership for p in selected_players)

        stack_positions, max_game_stack, max_game_key, stack_count, all_game_stacks, rb_dst_stack = compute_stack_positions(selected_players)

        lineup = LineupResult(
            players=tuple(selected_players),
            total_projection=total_projection,
            total_salary=total_salary,
            sum_ownership=sum_ownership,
            product_ownership=product_ownership,
            weighted_ownership=weighted_ownership,
            stack_positions=stack_positions,
            max_game_stack=max_game_stack,
            max_game_key=max_game_key,
            stack_count=stack_count,
            all_game_stacks=all_game_stacks,
            rb_dst_stack=rb_dst_stack,
        )
        lineups.append(lineup)
        previous_solutions.append(selected_idxs)

        # Add uniqueness constraint to avoid reproducing the same lineup
        prob += pulp.lpSum(x[i] for i in selected_idxs) <= 8

    return lineups


def lineups_to_dataframe(lineups: List[LineupResult]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for i, lu in enumerate(sorted(lineups, key=lambda l: l.total_projection, reverse=True), start=1):
        row = lu.to_row()
        row["Rank"] = i
        rows.append(row)
    cols = [
        "Rank",
        "Projection",
        "Salary",
        "Sum Ownership",
        "Product Ownership",
        "Weighted Ownership",
        "# Stacked",
        "QB Stack",
        "RB/DST Stack",
        "Game Stack",
        "QB",
        "RB1",
        "RB2",
        "WR1",
        "WR2",
        "WR3",
        "TE",
        "FLEX",
        "DST",
    ]
    df = pd.DataFrame(rows)
    # Ensure all expected columns exist
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]
