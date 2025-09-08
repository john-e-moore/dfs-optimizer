from __future__ import annotations

import argparse
import sys

import pandas as pd

from .data_loader import load_and_clean
from .models import players_from_df, Parameters
from .optimizer import generate_lineups, lineups_to_dataframe
from .filters import filter_lineups
from .reporting import export_workbook
from .logging_utils import setup_logger

logger = setup_logger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DFS Lineup Optimizer")
    p.add_argument("--projections", type=str, required=False,
                   default="data/DraftKings NFL DFS Projections -- Main Slate.csv",
                   help="Path to projections CSV")
    p.add_argument("--lineups", type=int, default=5000)
    p.add_argument("--min-salary", type=int, default=45000)
    p.add_argument("--allow-qb-vs-dst", action="store_true")
    p.add_argument("--stack", type=int, default=1)
    p.add_argument("--game-stack", type=int, default=0)
    # Filters
    p.add_argument("--min-player-projection", type=float, default=None)
    p.add_argument("--min-sum-ownership", type=float, default=None,
                   help="Fraction 0..1")
    p.add_argument("--max-sum-ownership", type=float, default=None,
                   help="Fraction 0..1")
    p.add_argument("--min-product-ownership", type=float, default=None)
    p.add_argument("--max-product-ownership", type=float, default=None)

    p.add_argument("--out-unfiltered", type=str, default="output/unfiltered_lineups.xlsx")
    p.add_argument("--out-filtered", type=str, default="output/filtered_lineups.xlsx")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    params = Parameters(
        lineup_count=args.lineups,
        min_salary=args.min_salary,
        allow_qb_vs_dst=args.allow_qb_vs_dst,
        stack=args.stack,
        game_stack=args.game_stack,
        min_player_projection=args.min_player_projection,
        min_sum_ownership=args.min_sum_ownership,
        max_sum_ownership=args.max_sum_ownership,
        min_product_ownership=args.min_product_ownership,
        max_product_ownership=args.max_product_ownership,
    )
    params.validate()

    cleaned = load_and_clean(args.projections)
    players = players_from_df(cleaned)

    logger.info("Generating lineups: target=%d", min(params.lineup_count, 5000))
    lineups = generate_lineups(players, params)
    unfiltered_df = lineups_to_dataframe(lineups)
    export_workbook(cleaned, params, unfiltered_df, args.out_unfiltered)

    fr = filter_lineups(lineups, params)
    filtered_df = lineups_to_dataframe(fr.lineups)
    export_workbook(cleaned, params, filtered_df, args.out_filtered)

    logger.info("Completed. Unfiltered=%d Filtered=%d Dropped=%d", len(unfiltered_df), len(filtered_df), fr.dropped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
