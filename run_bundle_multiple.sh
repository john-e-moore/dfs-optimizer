#!/usr/bin/env bash
set -euo pipefail

# Execute run_bundle.sh for each bundle defined in run_full.sh.
# A bundle is defined by a comment line followed by several `bash run.sh ...` lines.
# The aggregated output filename is derived from the comment, e.g.:
#   "Flat small (<1k)" -> output/<ts>/flat_small_u1k.xlsx

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FULL_SCRIPT="$SCRIPT_DIR/run_full.sh"

if [[ ! -f "$FULL_SCRIPT" ]]; then
	echo "Could not find run_full.sh at $FULL_SCRIPT" >&2
	exit 1
fi

# Prefer a shared timestamp across all bundles for organization
TS="${BUNDLE_MULTIPLE_TIMESTAMP:-$(date '+%Y%m%d_%H%M%S')}"

log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

sanitize_title_to_basename() {
	# Convert a section title like: "Flat small (<1k)" -> "flat_small_u1k"
	local title="$1"
	local base paren suffix cleaned
	paren="$(printf '%s' "$title" | sed -nE 's/.*\(([^)]*)\).*/\1/p')"
	base="$(printf '%s' "$title" | sed -E 's/\([^)]*\)//g' | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/_+/_/g; s/^_|_$//g')"
	if [[ -n "$paren" ]]; then
		paren="$(printf '%s' "$paren" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
		if [[ "$paren" == \<* ]]; then
			suffix="u${paren#<}"
		elif [[ "$paren" == \>* ]]; then
			suffix="o${paren#>}"
		elif [[ "$paren" == *-* ]]; then
			suffix="${paren//-/_}"
		else
			suffix="${paren//[^a-z0-9]/_}"
		fi
		cleaned="${base}_${suffix}"
	else
		cleaned="$base"
	fi
	printf '%s' "$cleaned"
}

run_section() {
	local section_title="$1"; shift
	local -a lines=("$@")
	if [[ ${#lines[@]} -eq 0 ]]; then
		return 0
	fi
	local basename outfile
	basename="$(sanitize_title_to_basename "$section_title")"
	outfile="output/${TS}/${basename}.xlsx"

	log "Bundling: $section_title -> $outfile"

	# Build BUNDLE_RUNS: each line is LABEL | ENV_ASSIGNMENTS | EXTRA_ARGS
	local idx=0
	local bundle_runs=""
	for line in "${lines[@]}"; do
		# Extract args after 'bash run.sh' (POSIX whitespace)
		args="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*bash[[:space:]]+run\.sh[[:space:]]*//')"
		idx=$((idx+1))
		label="Run${idx}"
		bundle_runs+="${label} |  | ${args}
"
	done

	# Execute bundler with shared timestamp
	BUNDLE_TIMESTAMP="$TS" BUNDLE_OUT="$outfile" BUNDLE_RUNS="$bundle_runs" bash "$SCRIPT_DIR/run_bundle.sh"
}

main() {
	log "Parsing $FULL_SCRIPT for bundle sections"
	local current_title=""
	local -a current_lines=()
	while IFS= read -r raw; do
		line="$raw"
		# Skip shebang
		if [[ "$line" =~ ^#! ]]; then
			continue
		fi
		# Section header: lines that start with '# ' (not shebang)
		if [[ "$line" =~ ^#[[:space:]] ]]; then
			# Flush previous section if present
			if [[ -n "$current_title" ]]; then
				run_section "$current_title" "${current_lines[@]}"
				current_lines=()
			fi
			# Strip leading '#'
			current_title="$(printf '%s' "$line" | sed -E 's/^#+[[:space:]]*//')"
			continue
		fi
		# Capture run lines
		if printf '%s' "$line" | grep -qE '^[[:space:]]*bash[[:space:]]+run\.sh\b'; then
			current_lines+=("$line")
		fi
	done < "$FULL_SCRIPT"
	# Flush last section
	if [[ -n "$current_title" ]]; then
		run_section "$current_title" "${current_lines[@]}"
	fi
	log "All bundles complete."
}

main "$@"
