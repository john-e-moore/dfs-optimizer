#!/usr/bin/env bash
set -euo pipefail

# Iterate all QBs and generate lineups per QB using ./run.sh, then aggregate
# results into a single workbook using tools/aggregate_lineups.py.

# Defaults (can be overridden by env)
: "${PROJECTIONS:=data/DraftKings NFL DFS Projections -- Main Slate.csv}"
: "${QB_STACKS_QB_LIST:=}"
: "${QB_STACKS_OUT_UNFILTERED:=output/qb_stacks_unfiltered.xlsx}"
: "${QB_STACKS_OUT_FILTERED:=output/qb_stacks_filtered.xlsx}"
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

# If using default aggregate output paths, place them under the timestamped directory
if [[ "$QB_STACKS_OUT_UNFILTERED" == "output/qb_stacks_unfiltered.xlsx" ]]; then
    QB_STACKS_OUT_UNFILTERED="${BASE_OUT_DIR}/qb_stacks_unfiltered.xlsx"
fi
if [[ "$QB_STACKS_OUT_FILTERED" == "output/qb_stacks_filtered.xlsx" ]]; then
    QB_STACKS_OUT_FILTERED="${BASE_OUT_DIR}/qb_stacks_filtered.xlsx"
fi

# Pick Python interpreter (prefer venv)
if [[ -x "venv/bin/python" ]]; then
    PYBIN="venv/bin/python"
else
    PYBIN="python"
fi

log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

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
path = sys.argv[1]
df = pd.read_csv(path)
if 'Position' not in df.columns or 'Name' not in df.columns:
    sys.exit(0)
qbs = sorted(set(str(n) for n in df.loc[df['Position'].astype(str).str.upper().eq('QB'), 'Name']))
for name in qbs:
    if name.strip():
        print(name.strip())
PY
}

main() {
    log "QB stacks: discovering quarterbacks..."
    mapfile -t QBS < <(discover_qbs)
    if [[ ${#QBS[@]} -eq 0 ]]; then
        log "No quarterbacks found; exiting."
        exit 1
    fi
    log "Found ${#QBS[@]} quarterbacks"

    # Collect sources for aggregation
    declare -a SRC_UNF=()
    declare -a SRC_FIL=()

    for qb in "${QBS[@]}"; do
        [[ -z "$qb" ]] && continue
        token="$(sanitize "$qb")"
        run_dir="${BASE_OUT_DIR}/qb_stacks/intermediate/${token}"
        out_unf="${run_dir}/unfiltered_lineups.xlsx"
        out_fil="${run_dir}/filtered_lineups.xlsx"
        mkdir -p "$run_dir"
        log "Running for QB: $qb"
        # Invoke run.sh with per-run outputs and include the QB
        INCLUDE_PLAYERS="$qb" OUT_UNFILTERED="$out_unf" OUT_FILTERED="$out_fil" ./run.sh || true
        # Append to sources if files exist
        if [[ -f "$out_unf" ]]; then
            SRC_UNF+=("${out_unf}::${qb}")
        else
            log "Warning: missing unfiltered output for $qb at $out_unf"
        fi
        if [[ -f "$out_fil" ]]; then
            SRC_FIL+=("${out_fil}::${qb}")
        else
            log "Warning: missing filtered output for $qb at $out_fil"
        fi
    done

    # Aggregate
    if (( ${#SRC_UNF[@]} > 0 )); then
        log "Aggregating unfiltered lineups -> $QB_STACKS_OUT_UNFILTERED"
        cmd=("$PYBIN" tools/aggregate_lineups.py --out "$QB_STACKS_OUT_UNFILTERED" --column-name QB)
        for s in "${SRC_UNF[@]}"; do
            cmd+=(--src "$s")
        done
        "${cmd[@]}"
    else
        log "No unfiltered sources to aggregate"
    fi
    if (( ${#SRC_FIL[@]} > 0 )); then
        log "Aggregating filtered lineups -> $QB_STACKS_OUT_FILTERED"
        cmd=("$PYBIN" tools/aggregate_lineups.py --out "$QB_STACKS_OUT_FILTERED" --column-name QB)
        for s in "${SRC_FIL[@]}"; do
            cmd+=(--src "$s")
        done
        "${cmd[@]}"
    else
        log "No filtered sources to aggregate"
    fi

    # Report per-QB counts from aggregated Summary and determine exit status
    total_unf=0
    total_fil=0

    if [[ -f "$QB_STACKS_OUT_UNFILTERED" ]]; then
        log "Summary (unfiltered):"
        mapfile -t SUMM < <("$PYBIN" - "$QB_STACKS_OUT_UNFILTERED" QB << 'PY'
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
    print(f"QB {name}: {cnt}")
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

    if [[ -f "$QB_STACKS_OUT_FILTERED" ]]; then
        log "Summary (filtered):"
        mapfile -t SUMM2 < <("$PYBIN" - "$QB_STACKS_OUT_FILTERED" QB << 'PY'
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
    print(f"QB {name}: {cnt}")
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


