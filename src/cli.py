from __future__ import annotations

import argparse
import sys
from typing import List, Set, Dict

import pandas as pd
import time
import os
from datetime import datetime

from .data_loader import load_and_clean
from .sabersim_loader import find_latest_sabersim_csv, load_and_clean_sabersim_csv
from .models import players_from_df, Parameters
from .optimizer import generate_lineups, lineups_to_dataframe
from .reporting import export_workbook
from .logging_utils import setup_logger
from .observability import (
    snapshot_cleaned_projections,
    snapshot_players_pool,
    snapshot_lineups,
    snapshot_parameters,
)
from .io_utils import ensure_dir
from .slate_loader import find_single_json_in_data, build_start_time_map, extract_games_table

logger = setup_logger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DFS Lineup Optimizer")
    p.add_argument("--projections", type=str, required=False,
                   default="data/projections_small.csv",
                   help="Path to projections CSV")
    p.add_argument("--ss", "--sabersim", dest="sabersim", action="store_true",
                   help="Load from latest data/NFL_*.csv SaberSim file instead of default projections")
    p.add_argument("--lineups", type=int, default=5000)
    p.add_argument("--min-salary", type=int, default=45000)
    p.add_argument("--allow-qb-vs-dst", action="store_true")
    p.add_argument("--stack", type=int, default=1)
    p.add_argument("--game-stack", type=int, default=0)
    p.add_argument("--game-stack-target", type=str, default=None,
                   help="Targeted game key (e.g., BUF/NYJ, NYJ@BUF, BUF-NYJ); order-insensitive")
    # Performance
    p.add_argument("--solver-threads", type=int, default=None, help="Number of solver threads")
    p.add_argument("--solver-time-limit-s", type=int, default=None, help="Solver time limit in seconds")
    # Filters / constraints
    p.add_argument("--min-sum-projection", type=float, default=None,
                   help="Minimum total projection per lineup (replaces --min-player-projection)")
    p.add_argument("--max-sum-projection", type=float, default=None,
                   help="Maximum total projection per lineup")
    p.add_argument("--min-sum-ownership", type=float, default=None,
                   help="Fraction 0..1")
    p.add_argument("--max-sum-ownership", type=float, default=None,
                   help="Fraction 0..1")
    p.add_argument("--min-product-ownership", type=float, default=None)
    p.add_argument("--max-product-ownership", type=float, default=None)
    p.add_argument("--min-weighted-ownership", type=float, default=None,
                   help="Sum over players of (salary/50000 * ownership); fraction 0..1")
    p.add_argument("--max-weighted-ownership", type=float, default=None,
                   help="Sum over players of (salary/50000 * ownership); fraction 0..1")

    # New pruning/constraints
    p.add_argument("--exclude-players", action="append", default=None,
                   help="Player names to exclude (comma-separated or repeat flag)")
    p.add_argument("--include-players", action="append", default=None,
                   help="Player names to force include in all lineups (comma-separated or repeat flag)")
    p.add_argument("--exclude-teams", action="append", default=None,
                   help="Teams to exclude (comma-separated or repeat flag; e.g., CAR or BUF,CAR)")
    p.add_argument("--min-team", action="append", default=None,
                   help="Minimum players by team, repeatable in TEAM:COUNT format (e.g., CAR:3)")
    p.add_argument("--rb-dst-stack", action="store_true",
                   help="Require an RB from the same team as the selected DST in each lineup")
    p.add_argument("--bringback", action="store_true",
                   help="Require at least one WR/TE from the opposing team of the selected QB")

    p.add_argument("--outdir", type=str, default="output/",
                   help="Directory to write timestamped run outputs")
    return p


def _parse_multi(values: List[str] | None) -> List[str]:
    if not values:
        return []
    items: List[str] = []
    for v in values:
        parts = [x.strip() for x in str(v).split(",") if str(x).strip()]
        items.extend(parts)
    return items


def _parse_min_team(values: List[str] | None) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not values:
        return out
    for v in values:
        parts = _parse_multi([v])
        for part in parts:
            if ":" not in part:
                raise SystemExit(f"Invalid --min-team value: '{part}'. Expected TEAM:COUNT")
            team, count_str = part.split(":", 1)
            team = team.strip().upper()
            try:
                count = int(count_str)
            except Exception:
                raise SystemExit(f"Invalid --min-team count in '{part}': must be integer")
            if count < 0:
                raise SystemExit(f"Invalid --min-team count in '{part}': must be non-negative")
            out[team] = count
    return out


def _normalize_ownership_fraction(value: float | None) -> float | None:
    """
    Accept both fraction (0..1) and percentage-style inputs (>1, e.g., 120 for 120%).
    Values greater than 2.0 are interpreted as percents and divided by 100.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return value
    if v > 2.0:
        return v / 100.0
    return v


def _compute_run_dir(outdir: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = outdir or "output/"
    run_dir = os.path.join(base, timestamp)
    ensure_dir(os.path.join(run_dir, "dummy"))
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    min_sum_projection = args.min_sum_projection
    max_sum_projection = args.max_sum_projection

    # Normalize list-like arguments
    excluded_players: Set[str] = set(_parse_multi(args.exclude_players)) if args.exclude_players is not None else set()
    included_players: Set[str] = set(_parse_multi(args.include_players)) if args.include_players is not None else set()
    excluded_teams: Set[str] = {s.upper() for s in _parse_multi(args.exclude_teams)} if args.exclude_teams is not None else set()
    min_players_by_team: Dict[str, int] = _parse_min_team(args.min_team)

    # Normalize game stack target to sorted AAA/BBB using '-' as canonical separator
    game_stack_target: str | None = None
    if args.game_stack_target:
        raw = str(args.game_stack_target).strip().upper()
        # Accept separators '/', '@', '-'
        for sep in ["/", "@", "-"]:
            raw = raw.replace(sep, "/")
        parts = [p for p in raw.split("/") if p]
        if len(parts) != 2:
            raise SystemExit(f"Invalid --game-stack-target '{args.game_stack_target}'. Expected TEAM1/TEAM2")
        a, b = sorted(parts)
        game_stack_target = f"{a}-{b}"

    # Normalize ownership thresholds to fractions if user passed percents like 120.0
    min_sum_ownership = _normalize_ownership_fraction(args.min_sum_ownership)
    max_sum_ownership = _normalize_ownership_fraction(args.max_sum_ownership)
    min_weighted_ownership = _normalize_ownership_fraction(args.min_weighted_ownership)
    max_weighted_ownership = _normalize_ownership_fraction(args.max_weighted_ownership)

    params = Parameters(
        lineup_count=args.lineups,
        min_salary=args.min_salary,
        allow_qb_vs_dst=args.allow_qb_vs_dst,
        stack=args.stack,
        game_stack=args.game_stack,
        game_stack_target=game_stack_target,
        min_sum_projection=min_sum_projection,
        max_sum_projection=max_sum_projection,
        min_sum_ownership=min_sum_ownership,
        max_sum_ownership=max_sum_ownership,
        min_product_ownership=args.min_product_ownership,
        max_product_ownership=args.max_product_ownership,
        min_weighted_ownership=min_weighted_ownership,
        max_weighted_ownership=max_weighted_ownership,
        excluded_players=excluded_players,
        included_players=included_players,
        excluded_teams=excluded_teams,
        min_players_by_team=min_players_by_team,
        rb_dst_stack=bool(args.rb_dst_stack),
        bringback=bool(args.bringback),
        solver_threads=args.solver_threads,
        solver_time_limit_s=args.solver_time_limit_s,
    )
    params.validate()

    # Load projections either from CSV (default) or SaberSim Excel when -ss is set
    if args.sabersim:
        try:
            xlsx_path = find_latest_sabersim_csv("data/", prefix="NFL_")
        except Exception as e:
            raise SystemExit(str(e))
        cleaned = load_and_clean_sabersim_csv(xlsx_path)
    else:
        cleaned = load_and_clean(args.projections)
    # Determine run directory
    run_dir = _compute_run_dir(args.outdir)
    # Save early snapshots to the run directory as well
    snapshot_cleaned_projections(cleaned, path=os.path.join(run_dir, "cleaned_projections.csv"))
    players = players_from_df(cleaned)
    snapshot_players_pool(cleaned, path=os.path.join(run_dir, "players_pool.csv"))

    logger.info("Generating lineups: target=%d", min(params.lineup_count, 5000))
    t0 = time.time()
    lineups = generate_lineups(players, params)
    elapsed = time.time() - t0
    # Load slate start times from a single JSON in data/; enforce presence
    try:
        json_path = find_single_json_in_data("data/")
    except Exception as e:
        raise SystemExit(str(e))
    if not json_path:
        raise SystemExit("No draftables JSON found in data/. Expected exactly one file.")
    try:
        start_time_map = build_start_time_map(json_path)
        games_df = extract_games_table(json_path)
        logger.info(
            "Loaded draftables JSON '%s'; start-time entries=%d; games=%d",
            os.path.basename(json_path),
            len(start_time_map),
            len(games_df) if games_df is not None else 0,
        )
    except Exception as e:
        raise SystemExit(f"Failed reading draftables JSON '{json_path}': {e}")
    df = lineups_to_dataframe(lineups, start_time_map=start_time_map)
    snapshot_lineups(lineups, path=os.path.join(run_dir, "lineups.json"))
    snapshot_parameters(params, path=os.path.join(run_dir, "parameters.json"))
    export_workbook(
        cleaned,
        params,
        df,
        os.path.join(run_dir, "lineups.xlsx"),
        start_time_map=start_time_map,
        games_df=games_df,
    )

    # Human-friendly timing
    if elapsed >= 120:
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        elapsed_str = f"{mins}m {secs}s"
    else:
        elapsed_str = f"{elapsed:.2f}s"
    if len(df) == 0:
        logger.info("Completed with 0 lineups. Constraints likely infeasible for current pool. Time=%s", elapsed_str)
    else:
        logger.info("Completed. Lineups=%d Time=%s", len(df), elapsed_str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


