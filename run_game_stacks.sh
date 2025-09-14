#!/usr/bin/env bash
set -euo pipefail

# Iterate all games and generate targeted game-stack lineups using ./run.sh, then
# aggregate results into a single workbook using tools/aggregate_lineups.py.

# Defaults (can be overridden by env)
: "${PROJECTIONS:=data/DraftKings NFL DFS Projections -- Main Slate.csv}"
: "${GAME_STACKS_GAME_LIST:=}"
: "${GAME_STACKS_OUT_UNFILTERED:=output/game_stacks_unfiltered.xlsx}"
: "${GAME_STACKS_OUT_FILTERED:=output/game_stacks_filtered.xlsx}"
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

# If using default aggregate output paths, place them under the timestamped directory
if [[ "$GAME_STACKS_OUT_UNFILTERED" == "output/game_stacks_unfiltered.xlsx" ]]; then
    GAME_STACKS_OUT_UNFILTERED="${BASE_OUT_DIR}/game_stacks_unfiltered.xlsx"
fi
if [[ "$GAME_STACKS_OUT_FILTERED" == "output/game_stacks_filtered.xlsx" ]]; then
    GAME_STACKS_OUT_FILTERED="${BASE_OUT_DIR}/game_stacks_filtered.xlsx"
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
    # Read raw game keys from stdin and print normalized AAA/BBB (sorted, uppercased)
    "$PYBIN" - << 'PY'
import sys
for line in sys.stdin:
    raw = str(line).strip().upper()
    if not raw:
        continue
    for sep in ['@', '-', '\\']:
        raw = raw.replace(sep, '/')
    parts = [p for p in raw.split('/') if p]
    if len(parts) != 2:
        continue
    a, b = sorted(parts)
    print(f"{a}/{b}")
PY
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
    declare -a SRC_UNF=()
    declare -a SRC_FIL=()

    for g in "${GAMES[@]}"; do
        [[ -z "$g" ]] && continue
        token="$(sanitize "$g")"
        run_dir="${BASE_OUT_DIR}/game_stacks/intermediate/${token}"
        out_unf="${run_dir}/unfiltered_lineups.xlsx"
        out_fil="${run_dir}/filtered_lineups.xlsx"
        mkdir -p "$run_dir"
        log "Running for Game: $g"
        # Invoke run.sh with per-run outputs and targeted game stack
        GAME_STACK_TARGET="$g" OUT_UNFILTERED="$out_unf" OUT_FILTERED="$out_fil" ./run.sh || true
        # Append to sources if files exist
        if [[ -f "$out_unf" ]]; then
            SRC_UNF+=("${out_unf}::${g}")
        else
            log "Warning: missing unfiltered output for $g at $out_unf"
        fi
        if [[ -f "$out_fil" ]]; then
            SRC_FIL+=("${out_fil}::${g}")
        else
            log "Warning: missing filtered output for $g at $out_fil"
        fi
    done

    # Aggregate (add Game column)
    if (( ${#SRC_UNF[@]} > 0 )); then
        log "Aggregating unfiltered lineups -> $GAME_STACKS_OUT_UNFILTERED"
        cmd=("$PYBIN" tools/aggregate_lineups.py --out "$GAME_STACKS_OUT_UNFILTERED" --column-name Game)
        for s in "${SRC_UNF[@]}"; do
            cmd+=(--src "$s")
        done
        "${cmd[@]}"
    else
        log "No unfiltered sources to aggregate"
    fi
    if (( ${#SRC_FIL[@]} > 0 )); then
        log "Aggregating filtered lineups -> $GAME_STACKS_OUT_FILTERED"
        cmd=("$PYBIN" tools/aggregate_lineups.py --out "$GAME_STACKS_OUT_FILTERED" --column-name Game)
        for s in "${SRC_FIL[@]}"; do
            cmd+=(--src "$s")
        done
        "${cmd[@]}"
    else
        log "No filtered sources to aggregate"
    fi

    # Report per-game counts from aggregated Summary and determine exit status
    total_unf=0
    total_fil=0

    if [[ -f "$GAME_STACKS_OUT_UNFILTERED" ]]; then
        log "Summary (unfiltered):"
        mapfile -t SUMM < <("$PYBIN" - "$GAME_STACKS_OUT_UNFILTERED" Game << 'PY'
import sys
import pandas as pd
path = sys.argv[1]
col = sys.argv[2]
try:
    df = pd.read_excel(path, sheet_name='Summary')
except Exception:
    print('TOTAL 0')
    raise SystemExit(0)
if df.empty or col not in df.columns or 'Lineups' not in df.columns:
    print('TOTAL 0')
    raise SystemExit(0)
for _, r in df.sort_values(by=['Lineups', col], ascending=[False, True]).iterrows():
    name = str(r[col])
    cnt = int(r['Lineups'])
    print(f"Game {name}: {cnt}")
print(f"TOTAL {int(df['Lineups'].sum())}")
PY
)
        for line in "${SUMM[@]}"; do
            if [[ "$line" == TOTAL* ]]; then
                total_unf=${line#TOTAL }
            else
                log "$line"
            fi
        done
        log "Total unfiltered lineups aggregated: $total_unf"
    fi

    if [[ -f "$GAME_STACKS_OUT_FILTERED" ]]; then
        log "Summary (filtered):"
        mapfile -t SUMM2 < <("$PYBIN" - "$GAME_STACKS_OUT_FILTERED" Game << 'PY'
import sys
import pandas as pd
path = sys.argv[1]
col = sys.argv[2]
try:
    df = pd.read_excel(path, sheet_name='Summary')
except Exception:
    print('TOTAL 0')
    raise SystemExit(0)
if df.empty or col not in df.columns or 'Lineups' not in df.columns:
    print('TOTAL 0')
    raise SystemExit(0)
for _, r in df.sort_values(by=['Lineups', col], ascending=[False, True]).iterrows():
    name = str(r[col])
    cnt = int(r['Lineups'])
    print(f"Game {name}: {cnt}")
print(f"TOTAL {int(df['Lineups'].sum())}")
PY
)
        for line in "${SUMM2[@]}"; do
            if [[ "$line" == TOTAL* ]]; then
                total_fil=${line#TOTAL }
            else
                log "$line"
            fi
        done
        log "Total filtered lineups aggregated: $total_fil"
    fi

    total_all=$(( total_unf + total_fil ))
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


