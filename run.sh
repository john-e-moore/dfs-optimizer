#!/usr/bin/env bash
set -euo pipefail

# Defaults (match CLI defaults); allow environment overrides if already set
: "${PROJECTIONS:=data/DraftKings NFL DFS Projections -- Main Slate.csv}"
: "${LINEUPS:=200}"
: "${MIN_SALARY:=49600}"
: "${STACK:=1}"
: "${GAME_STACK:=0}"
: "${GAME_STACK_TARGET:=}"
: "${OUTDIR:=output}"

# Optional flags (left empty to use defaults); environment can override
: "${ALLOW_QB_VS_DST:=}"
: "${MIN_SUM_PROJECTION:=}"
: "${MIN_SUM_OWNERSHIP:=}"
: "${MAX_SUM_OWNERSHIP:=100}"
: "${MIN_PRODUCT_OWNERSHIP:=}"
: "${MAX_PRODUCT_OWNERSHIP:=}"
: "${EXCLUDE_PLAYERS:=}" # "Joe Burrow,Patrick Mahomes"
: "${INCLUDE_PLAYERS:=}"
: "${EXCLUDE_TEAMS:=}"
: "${MIN_TEAM:=}"
: "${RB_DST_STACK:=}"
: "${SOLVER_THREADS:=5}"
: "${SOLVER_TIME_LIMIT_S:=}"

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
	${GAME_STACK_TARGET:+--game-stack-target "$GAME_STACK_TARGET"}
	--outdir "$OUTDIR"
)

# Conditionally add optional flags if variables are set
[[ -n "$ALLOW_QB_VS_DST" ]] && ARGS+=(--allow-qb-vs-dst)
[[ -n "$MIN_SUM_PROJECTION" ]] && ARGS+=(--min-sum-projection "$MIN_SUM_PROJECTION")
[[ -n "$MIN_SUM_OWNERSHIP" ]] && ARGS+=(--min-sum-ownership "$MIN_SUM_OWNERSHIP")
[[ -n "$MAX_SUM_OWNERSHIP" ]] && ARGS+=(--max-sum-ownership "$MAX_SUM_OWNERSHIP")
[[ -n "$MIN_PRODUCT_OWNERSHIP" ]] && ARGS+=(--min-product-ownership "$MIN_PRODUCT_OWNERSHIP")
[[ -n "$MAX_PRODUCT_OWNERSHIP" ]] && ARGS+=(--max-product-ownership "$MAX_PRODUCT_OWNERSHIP")
[[ -n "$SOLVER_THREADS" ]] && ARGS+=(--solver-threads "$SOLVER_THREADS")
[[ -n "$SOLVER_TIME_LIMIT_S" ]] && ARGS+=(--solver-time-limit-s "$SOLVER_TIME_LIMIT_S")
[[ -n "$EXCLUDE_PLAYERS" ]] && ARGS+=(--exclude-players "$EXCLUDE_PLAYERS")
[[ -n "$INCLUDE_PLAYERS" ]] && ARGS+=(--include-players "$INCLUDE_PLAYERS")
[[ -n "$EXCLUDE_TEAMS" ]] && ARGS+=(--exclude-teams "$EXCLUDE_TEAMS")
[[ -n "$MIN_TEAM" ]] && ARGS+=(--min-team "$MIN_TEAM")
if [[ -n "$RB_DST_STACK" ]]; then
	case "${RB_DST_STACK,,}" in
		1|true|yes|on|enable)
			ARGS+=(--rb-dst-stack)
			;;
	esac
fi

# Run optimizer
python -m src.cli "${ARGS[@]}"

# Discover the latest run directory under OUTDIR and echo it for callers
if [[ -d "$OUTDIR" ]]; then
    # Find newest timestamped subdirectory containing lineups.xlsx
    RUN_DIR=""
    while IFS= read -r -d '' d; do
        if [[ -f "$d/lineups.xlsx" ]]; then
            RUN_DIR="$d"
            break
        fi
    done < <(ls -1dt "$OUTDIR"/*/ 2>/dev/null | tr -d '\n' | xargs -0 -I {} echo -n {})
    # Fallback to newest subdir
    if [[ -z "$RUN_DIR" ]]; then
        RUN_DIR="$(ls -1dt "$OUTDIR"/*/ 2>/dev/null | head -n1 | sed 's:/*$::')"
    else
        RUN_DIR="${RUN_DIR%/}"
    fi
    echo "RUN_DIR=$RUN_DIR"
fi
