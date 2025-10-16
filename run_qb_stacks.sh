#!/usr/bin/env bash
set -euo pipefail

# Iterate all QBs and generate lineups per QB using ./run.sh, then aggregate
# results into a single workbook using tools/aggregate_lineups.py.

# Defaults (can be overridden by env)
: "${PROJECTIONS:=data/DraftKings NFL DFS Projections -- Main Slate.csv}"
: "${QB_STACKS_QB_LIST:=}"
: "${QB_STACKS_OUT:=output/qb_stacks.xlsx}"
: "${QB_STACKS_KEEP_INTERMEDIATE:=1}"
: "${QB_STACKS_TIMESTAMP:=}"

# Establish timestamped base output directory similar to run.sh default behavior
if [[ -n "$QB_STACKS_TIMESTAMP" ]]; then
    TS="$QB_STACKS_TIMESTAMP"
else
    TS="$(date '+%Y%m%d_%H%M%S')"
fi
BASE_OUT_DIR="output/${TS}"
mkdir -p "$BASE_OUT_DIR"

# Log all script output into timestamped folder
STACKS_LOG="${BASE_OUT_DIR}/run_qb_stacks.log"
exec > >(tee -a "$STACKS_LOG") 2>&1

# If using default aggregate output path, place it under the timestamped directory
if [[ "$QB_STACKS_OUT" == "output/qb_stacks.xlsx" ]]; then
    QB_STACKS_OUT="${BASE_OUT_DIR}/qb_stacks.xlsx"
fi

# Pick Python interpreter (prefer venv)
if [[ -x "venv/bin/python" ]]; then
    PYBIN="venv/bin/python"
else
    PYBIN="python"
fi

log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

# Resolve projections path based on --ss flag or SABERSIM env
resolve_projections_from_args() {
    local use_ss=""
    # Detect --ss or -ss in args
    for arg in "$@"; do
        if [[ "$arg" == "--ss" || "$arg" == "-ss" ]]; then
            use_ss=1
            break
        fi
    done
    # Also honor SABERSIM env toggle
    if [[ -z "$use_ss" && -n "${SABERSIM:-}" ]]; then
        case "${SABERSIM,,}" in
            1|true|yes|on|enable)
                use_ss=1
                ;;
        esac
    fi
    if [[ -n "$use_ss" ]]; then
        # Pick the most recent SaberSim-style file
        local latest
        latest="$(ls -1t data/NFL_*.csv data/NFL_*.xlsx 2>/dev/null | head -n1 || true)"
        if [[ -n "$latest" ]]; then
            PROJECTIONS="$latest"
            log "Using SaberSim projections: $PROJECTIONS"
        else
            log "Warning: --ss provided but no data/NFL_*.csv|.xlsx found; falling back to PROJECTIONS=$PROJECTIONS"
        fi
    fi
}

sanitize() {
    # Make a filesystem-safe token from a QB name
    # Keep alnum, dash, underscore; replace spaces with underscore; drop others
    local s="$1"
    s="${s// /_}"
    s="$(printf '%s' "$s" | tr -cd '[:alnum:]_-')"
    printf '%s' "$s"
}

discover_qbs() {
    # If QB list provided, echo one per line; else parse from projections via pandas
    if [[ -n "$QB_STACKS_QB_LIST" ]]; then
        # split by comma
        awk -v str="$QB_STACKS_QB_LIST" 'BEGIN{n=split(str,a,","); for(i=1;i<=n;i++){gsub(/^ +| +$/,"",a[i]); if(a[i] != "") print a[i]}}'
        return 0
    fi
    "$PYBIN" - "$PROJECTIONS" << 'PY'
import sys
import pandas as pd
import os
path = sys.argv[1]
ext = os.path.splitext(path)[1].lower()
if ext in ('.xls', '.xlsx'):
    df = pd.read_excel(path)
else:
    df = pd.read_csv(path)
cols = {str(c).strip(): c for c in df.columns}
name_col = cols.get('Name')
pos_col = cols.get('Position') or cols.get('Pos')
if not name_col or not pos_col:
    sys.exit(0)
qbs = sorted(set(str(n).strip() for n in df.loc[df[pos_col].astype(str).str.upper().eq('QB'), name_col]))
for name in qbs:
    if name:
        print(name)
PY
}

main() {
    # Resolve projections before discovering QBs
    resolve_projections_from_args "$@"
    log "QB stacks: discovering quarterbacks..."
    mapfile -t QBS < <(discover_qbs)
    if [[ ${#QBS[@]} -eq 0 ]]; then
        log "No quarterbacks found; exiting."
        exit 1
    fi
    log "Found ${#QBS[@]} quarterbacks"

    # Collect sources for aggregation
    declare -a SRC_ALL=()

    for qb in "${QBS[@]}"; do
        [[ -z "$qb" ]] && continue
        token="$(sanitize "$qb")"
        run_dir="${BASE_OUT_DIR}/qb_stacks/intermediate/${token}"
        mkdir -p "$run_dir"
        log "Running for QB: $qb"
        # Invoke run.sh with per-run outdir and include the QB; pass PROJECTIONS through
        INCLUDE_PLAYERS="$qb" OUTDIR="$run_dir" PROJECTIONS="$PROJECTIONS" ./run.sh "$@" || true
        # Determine the timestamped child run directory
        latest_child="$(ls -1dt "$run_dir"/*/ 2>/dev/null | head -n1 | sed 's:/*$::')"
        out_xlsx="${latest_child}/lineups.xlsx"
        # Append to sources if file exists
        if [[ -n "$latest_child" && -f "$out_xlsx" ]]; then
            SRC_ALL+=("${out_xlsx}::${qb}")
        else
            log "Warning: missing output for $qb at $out_xlsx"
        fi
    done

    # Aggregate
    if (( ${#SRC_ALL[@]} > 0 )); then
        log "Aggregating lineups -> $QB_STACKS_OUT"
        cmd=("$PYBIN" tools/aggregate_lineups.py --out "$QB_STACKS_OUT" --column-name QB)
        for s in "${SRC_ALL[@]}"; do
            cmd+=(--src "$s")
        done
        "${cmd[@]}"
    else
        log "No sources to aggregate"
    fi

    # Determine total by reading Lineups sheet row count
    total_all=0
    if [[ -f "$QB_STACKS_OUT" ]]; then
        total_all="$($PYBIN - "$QB_STACKS_OUT" << 'PY'
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
        log "No feasible lineups found across all QBs. Exiting with non-zero status."
        exit 1
    fi

    # Cleanup intermediates if requested
    if [[ -n "$QB_STACKS_KEEP_INTERMEDIATE" ]]; then
        case "${QB_STACKS_KEEP_INTERMEDIATE,,}" in
            0|false|no|off|disable) 
                log "Cleaning up intermediate outputs under ${BASE_OUT_DIR}/qb_stacks/intermediate"
                rm -rf "${BASE_OUT_DIR}/qb_stacks/intermediate" || true
                ;;
        esac
    fi

    log "QB stacks complete."
}

main "$@"


