#!/usr/bin/env bash
set -euo pipefail

# Run multiple labeled invocations of ./run.sh then aggregate all outputs into a single workbook.
#
# There are two ways to provide runs:
# 1) Via a runs file: --runs-file path/to/runs.txt
#    Each non-empty, non-comment line has up to three pipe-delimited fields:
#        LABEL | ENV_ASSIGNMENTS | EXTRA_ARGS
#    - LABEL: a short name for the run (used in aggregation and folder names)
#    - ENV_ASSIGNMENTS: optional shell snippet like: LINEUPS=300 STACK=2 BRINGBACK=1
#    - EXTRA_ARGS: optional additional CLI flags passed to ./run.sh, e.g.: --ss --max-weighted-ownership 19
#    Quotes are supported in fields 2 and 3 (they are executed in a shell).
#
# 2) Via the BUNDLE_RUNS environment variable as a multi-line string with the same format as above.
#    Example:
#        BUNDLE_RUNS='\
#        Flat1 | LINEUPS=250 STACK=1 MIN_SALARY=49600 | --ss --max-weighted-ownership 20\
#        Flat2 | LINEUPS=250 STACK=2 MIN_SALARY=49600 | --ss --max-weighted-ownership 19\
#        Flat2BB | LINEUPS=250 STACK=2 BRINGBACK=1 MIN_SALARY=49600 | --ss --max-weighted-ownership 19\
#        '
#
# Outputs are written under output/<timestamp>/bundle/...
# The aggregated workbook defaults to output/<timestamp>/bundle.xlsx unless BUNDLE_OUT is set.

: "${BUNDLE_OUT:=output/bundle.xlsx}"
: "${BUNDLE_COLUMN_NAME:=Bundle}"
: "${BUNDLE_KEEP_INTERMEDIATE:=1}"
: "${BUNDLE_TIMESTAMP:=}"

# Pick Python interpreter (prefer venv)
if [[ -x "venv/bin/python" ]]; then
	PYBIN="venv/bin/python"
else
	PYBIN="python"
fi

log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

sanitize() {
	# Make a filesystem-safe token from a label
	local s="$1"
	s="${s// /_}"
	s="$(printf '%s' "$s" | tr -cd '[:alnum:]_-')"
	printf '%s' "$s"
}

trim() { awk '{gsub(/^ +| +$/,"",$0); print}'; }

normalize_spec_lines() {
	# Read raw lines, remove comments/blank, and produce tab-delimited LABEL\tENV\tARGS
	awk '
		BEGIN{FS="|"}
		{
			# Strip comments starting with # (not within quotes; good enough heuristically)
			line=$0
			sub(/#.*/, "", line)
			gsub(/^\t+|\t+$/, "", line)
			gsub(/^ +| +$/, "", line)
			if (length(line)==0) next
			n=split(line, parts, "|")
			for (i=1;i<=n;i++){ gsub(/^ +| +$/, "", parts[i]) }
			label=(n>=1?parts[1]:"")
			env=(n>=2?parts[2]:"")
			args=(n>=3?parts[3]:"")
			if (label!="") printf "%s\t%s\t%s\n", label, env, args
		}
	'
}

read_runs_from_file() {
	local path="$1"
	if [[ ! -f "$path" ]]; then
		printf "Error: runs file not found: %s\n" "$path" >&2
		return 1
	fi
	cat "$path" | normalize_spec_lines
}

read_runs_from_env() {
	if [[ -z "${BUNDLE_RUNS:-}" ]]; then
		return 1
	fi
	printf "%s\n" "$BUNDLE_RUNS" | normalize_spec_lines
}

main() {
	local runs_file=""
	while (( "$#" )); do
		case "$1" in
			--runs-file)
				shift; runs_file="${1:-}"; shift || true ;;
			*)
				# Forward any unknown flags to ./run.sh for each run
				# (we will append them after per-line args)
				EXTRA_GLOBAL_ARGS+=("$1"); shift ;;
		esac
	done

	# Establish timestamped base output directory
	local TS
	if [[ -n "$BUNDLE_TIMESTAMP" ]]; then
		TS="$BUNDLE_TIMESTAMP"
	else
		TS="$(date '+%Y%m%d_%H%M%S')"
	fi
	local BASE_OUT_DIR="output/${TS}"
	mkdir -p "$BASE_OUT_DIR/bundle/intermediate"

	# Log to file and stdout
	local BUNDLE_LOG="${BASE_OUT_DIR}/run_bundle.log"
	exec > >(tee -a "$BUNDLE_LOG") 2>&1

	# If using default aggregate output path, place it under the timestamped directory
	if [[ "$BUNDLE_OUT" == "output/bundle.xlsx" ]]; then
		BUNDLE_OUT="${BASE_OUT_DIR}/bundle.xlsx"
	fi

	log "Bundle: collecting run specifications"
	local have_specs=0
	local spec_stream
	if [[ -n "$runs_file" ]]; then
		spec_stream=$(read_runs_from_file "$runs_file") || true
	else
		spec_stream=$(read_runs_from_env) || true
	fi
	if [[ -n "${spec_stream:-}" ]]; then
		have_specs=1
	fi
	if (( have_specs == 0 )); then
		log "No runs specified. Provide --runs-file or set BUNDLE_RUNS. Exiting."
		exit 1
	fi

	log "Parsing run specs and executing runs..."

	declare -a SRC_ALL=()
	while IFS=$'\t' read -r label env_snippet args_snippet; do
		[[ -z "$label" ]] && continue
		token="$(sanitize "$label")"
		run_dir="${BASE_OUT_DIR}/bundle/intermediate/${token}"
		mkdir -p "$run_dir"
		log "Running: $label"
		# Compose a shell command so that quotes in env/args are respected
		cmd="OUTDIR=\"$run_dir\" ${env_snippet:-} ./run.sh ${args_snippet:-}"
		# If global extra args were provided, append them
		if [[ ${#EXTRA_GLOBAL_ARGS[@]:-0} -gt 0 ]]; then
			for ga in "${EXTRA_GLOBAL_ARGS[@]}"; do
				cmd+=" ${ga}"
			done
		fi
		# Execute via bash -lc to allow proper parsing of quotes
		bash -lc "$cmd" || true
		# Find latest child output
		latest_child="$(ls -1dt "$run_dir"/*/ 2>/dev/null | head -n1 | sed 's:/*$::')"
		out_xlsx="${latest_child}/lineups.xlsx"
		if [[ -n "$latest_child" && -f "$out_xlsx" ]]; then
			SRC_ALL+=("${out_xlsx}::${label}")
			log "Collected: ${out_xlsx}"
		else
			log "Warning: missing output for $label at $out_xlsx"
		fi
	done < <(printf "%s\n" "$spec_stream")

	if (( ${#SRC_ALL[@]} == 0 )); then
		log "No sources collected; exiting with non-zero status."
		exit 1
	fi

	log "Aggregating ${#SRC_ALL[@]} sources -> $BUNDLE_OUT"
	cmd=("$PYBIN" tools/aggregate_lineups.py --out "$BUNDLE_OUT" --column-name "$BUNDLE_COLUMN_NAME")
	for s in "${SRC_ALL[@]}"; do
		cmd+=(--src "$s")
	done
	"${cmd[@]}"

	# Determine total by reading Lineups sheet row count
	local total_all=0
	if [[ -f "$BUNDLE_OUT" ]]; then
		total_all="$($PYBIN - "$BUNDLE_OUT" << 'PY'
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
		log "No feasible lineups found across all runs. Exiting with non-zero status."
		exit 1
	fi

	# Cleanup intermediates if requested
	if [[ -n "$BUNDLE_KEEP_INTERMEDIATE" ]]; then
		case "${BUNDLE_KEEP_INTERMEDIATE,,}" in
			0|false|no|off|disable)
				log "Cleaning up intermediate outputs under ${BASE_OUT_DIR}/bundle/intermediate"
				rm -rf "${BASE_OUT_DIR}/bundle/intermediate" || true
				;;
		esac
	fi

	log "Bundle complete."
}

main "$@"
