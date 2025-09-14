#!/usr/bin/env bash
set -euo pipefail

# Iterate all games and generate targeted game-stack lineups using ./run.sh, then
# aggregate results into a single workbook using tools/aggregate_lineups.py.

# Defaults (can be overridden by env)
: "${PROJECTIONS:=data/DraftKings NFL DFS Projections -- Main Slate.csv}"
: "${GAME_STACKS_GAME_LIST:=}"
: "${GAME_STACKS_OUT:=output/game_stacks.xlsx}"
: "${GAME_STACKS_KEEP_INTERMEDIATE:=1}"
: "${GAME_STACKS_TIMESTAMP:=}"

# Enforce GAME_STACK > 0 if explicitly provided (do not override run.sh defaults)
if [[ -n "${GAME_STACK:-}" ]]; then
    # Accept numeric strings only; treat non-numeric as error
    if ! [[ "$GAME_STACK" =~ ^-?[0-9]+$ ]]; then
        echo "Invalid GAME_STACK='$GAME_STACK' (must be integer)" >&2
        exit 1
    fi
    if (( GAME_STACK <= 0 )); then
        echo "GAME_STACK must be > 0 for game stacks. Current GAME_STACK=$GAME_STACK" >&2
        exit 1
    fi
fi

# Establish timestamped base output directory similar to run.sh default behavior
if [[ -n "$GAME_STACKS_TIMESTAMP" ]]; then
    TS="$GAME_STACKS_TIMESTAMP"
else
    TS="$(date '+%Y%m%d_%H%M%S')"
fi
BASE_OUT_DIR="output/${TS}"
mkdir -p "$BASE_OUT_DIR"

# Log all script output into timestamped folder
STACKS_LOG="${BASE_OUT_DIR}/run_game_stacks.log"
exec > >(tee -a "$STACKS_LOG") 2>&1

# If using default aggregate output path, place it under the timestamped directory
if [[ "$GAME_STACKS_OUT" == "output/game_stacks.xlsx" ]]; then
    GAME_STACKS_OUT="${BASE_OUT_DIR}/game_stacks.xlsx"
fi

# Pick Python interpreter (prefer venv)
if [[ -x "venv/bin/python" ]]; then
    PYBIN="venv/bin/python"
else
    PYBIN="python"
fi

log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

sanitize() {
    # Make a filesystem-safe token from a game key like AAA/BBB
    local s="$1"
    s="${s//\//_}"
    s="$(printf '%s' "$s" | tr -cd '[:alnum:]_-')"
    printf '%s' "$s"
}

normalize_games_from_stdin() {
    # Read raw keys and normalize to AAA/BBB using awk
    awk '{
        raw = toupper($0);
        gsub(/[@-]/, "/", raw);
        n = split(raw, parts, "/");
        c = 0;
        delete a;
        for (i=1;i<=n;i++) { if (length(parts[i])>0) { c++; a[c]=parts[i] } }
        if (c==2) {
            if (a[1] <= a[2]) { printf "%s/%s\n", a[1], a[2] } else { printf "%s/%s\n", a[2], a[1] }
        }
    }'
}

discover_games() {
    # If game list provided, normalize and echo one per line; else parse from projections via pandas
    if [[ -n "$GAME_STACKS_GAME_LIST" ]]; then
        awk -v str="$GAME_STACKS_GAME_LIST" 'BEGIN{n=split(str,a,","); for(i=1;i<=n;i++){gsub(/^ +| +$/,"",a[i]); if(a[i] != "") print a[i]}}' | \
        normalize_games_from_stdin | sort -u
        return 0
    fi
    "$PYBIN" - "$PROJECTIONS" << 'PY'
import sys
import pandas as pd
path = sys.argv[1]
try:
    df = pd.read_csv(path)
except Exception:
    sys.exit(0)
if 'Team' not in df.columns or 'Opponent' not in df.columns:
    sys.exit(0)
games = set()
for _, row in df[['Team','Opponent']].dropna().iterrows():
    t = str(row['Team']).strip().upper()
    o = str(row['Opponent']).strip().upper()
    if not t or not o:
        continue
    a, b = sorted([t, o])
    games.add(f"{a}/{b}")
for g in sorted(games):
    print(g)
PY
}

main() {
    log "Game stacks: discovering games..."
    mapfile -t GAMES < <(discover_games)
    if [[ ${#GAMES[@]} -eq 0 ]]; then
        log "No games found; exiting."
        exit 1
    fi
    log "Found ${#GAMES[@]} games"

    # Collect sources for aggregation
    declare -a SRC_ALL=()

    for g in "${GAMES[@]}"; do
        [[ -z "$g" ]] && continue
        token="$(sanitize "$g")"
        run_dir="${BASE_OUT_DIR}/game_stacks/intermediate/${token}"
        mkdir -p "$run_dir"
        log "Running for Game: $g"
        # Invoke run.sh with per-run output directory and targeted game stack
        GAME_STACK_TARGET="$g" OUTDIR="$run_dir" ./run.sh || true
        # Determine the timestamped child run directory
        latest_child="$(ls -1dt "$run_dir"/*/ 2>/dev/null | head -n1 | sed 's:/*$::')"
        out_xlsx="${latest_child}/lineups.xlsx"
        # Append to sources if file exists
        if [[ -n "$latest_child" && -f "$out_xlsx" ]]; then
            SRC_ALL+=("${out_xlsx}::${g}")
        else
            log "Warning: missing output for $g at $out_xlsx"
        fi
    done

    # Aggregate (add Game column)
    if (( ${#SRC_ALL[@]} > 0 )); then
        log "Aggregating lineups -> $GAME_STACKS_OUT"
        cmd=("$PYBIN" tools/aggregate_lineups.py --out "$GAME_STACKS_OUT" --column-name Game)
        for s in "${SRC_ALL[@]}"; do
            cmd+=(--src "$s")
        done
        "${cmd[@]}"
    else
        log "No sources to aggregate"
    fi

    # Determine total by reading Lineups sheet row count
    total_all=0
    if [[ -f "$GAME_STACKS_OUT" ]]; then
        total_all="$($PYBIN - "$GAME_STACKS_OUT" << 'PY'
import sys, pandas as pd
path = sys.argv[1]
try:
    df = pd.read_excel(path, sheet_name='Lineups')
    print(len(df))
except Exception:
    print(0)
PY
)"
        log "Total lineups aggregated: $total_all"
    fi

    if (( total_all == 0 )); then
        log "No feasible lineups found across all games. Exiting with non-zero status."
        exit 1
    fi

    # Cleanup intermediates if requested
    if [[ -n "$GAME_STACKS_KEEP_INTERMEDIATE" ]]; then
        case "${GAME_STACKS_KEEP_INTERMEDIATE,,}" in
            0|false|no|off|disable)
                log "Cleaning up intermediate outputs under ${BASE_OUT_DIR}/game_stacks/intermediate"
                rm -rf "${BASE_OUT_DIR}/game_stacks/intermediate" || true
                ;;
        esac
    fi

    log "Game stacks complete."
}

main "$@"


