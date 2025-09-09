#!/usr/bin/env bash
set -euo pipefail

# Defaults (match CLI defaults)
PROJECTIONS="data/DraftKings NFL DFS Projections -- Main Slate.csv"
LINEUPS=100
MIN_SALARY=49800
STACK=1
GAME_STACK=0
OUT_UNFILTERED="output/unfiltered_lineups.xlsx"
OUT_FILTERED="output/filtered_lineups.xlsx"

# Optional flags (left empty to use defaults)
ALLOW_QB_VS_DST=""            # set to any non-empty value to enable flag
MIN_PLAYER_PROJECTION=""      # e.g., 1.0
MIN_SUM_OWNERSHIP=""          # fraction in [0,1], e.g., 0.9
MAX_SUM_OWNERSHIP=""          # fraction in [0,1], e.g., 1.4
MIN_PRODUCT_OWNERSHIP=""      # e.g., 1e-9
MAX_PRODUCT_OWNERSHIP=""      # e.g., 0.1
SOLVER_THREADS=""             # e.g., 2
SOLVER_TIME_LIMIT_S=""        # e.g., 30 (seconds)

# Activate venv if present
if [[ -f "venv/bin/activate" ]]; then
	# shellcheck disable=SC1091
	source "venv/bin/activate"
fi

ARGS=(
	--projections "$PROJECTIONS"
	--lineups "$LINEUPS"
	--min-salary "$MIN_SALARY"
	--stack "$STACK"
	--game-stack "$GAME_STACK"
	--out-unfiltered "$OUT_UNFILTERED"
	--out-filtered "$OUT_FILTERED"
)

# Conditionally add optional flags if variables are set
[[ -n "$ALLOW_QB_VS_DST" ]] && ARGS+=(--allow-qb-vs-dst)
[[ -n "$MIN_PLAYER_PROJECTION" ]] && ARGS+=(--min-player-projection "$MIN_PLAYER_PROJECTION")
[[ -n "$MIN_SUM_OWNERSHIP" ]] && ARGS+=(--min-sum-ownership "$MIN_SUM_OWNERSHIP")
[[ -n "$MAX_SUM_OWNERSHIP" ]] && ARGS+=(--max-sum-ownership "$MAX_SUM_OWNERSHIP")
[[ -n "$MIN_PRODUCT_OWNERSHIP" ]] && ARGS+=(--min-product-ownership "$MIN_PRODUCT_OWNERSHIP")
[[ -n "$MAX_PRODUCT_OWNERSHIP" ]] && ARGS+=(--max-product-ownership "$MAX_PRODUCT_OWNERSHIP")
[[ -n "$SOLVER_THREADS" ]] && ARGS+=(--solver-threads "$SOLVER_THREADS")
[[ -n "$SOLVER_TIME_LIMIT_S" ]] && ARGS+=(--solver-time-limit-s "$SOLVER_TIME_LIMIT_S")

python -m dfs_optimizer.cli "${ARGS[@]}"
