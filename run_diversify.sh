#!/usr/bin/env bash
set -euo pipefail

# Wrapper for diversified lineup selection (Jaccard).

# Prefer venv python if available
if [[ -x "venv/bin/python" ]]; then
    PYBIN="venv/bin/python"
else
    PYBIN="python"
fi

if [[ $# -eq 0 ]]; then
    # No args provided: run the default diversified selection used previously in diversify.sh
    DEFAULT_ARGS=(
        --input output/20251109_115529/small_u1k.xlsx
        --input output/20251109_115529/medium_1k_3k.xlsx
        --input output/20251109_115529/large_o3k.xlsx
        --pick output/20251109_115529/small_u1k.xlsx:5
        --pick output/20251109_115529/medium_1k_3k.xlsx:6
        --pick output/20251109_115529/large_o3k.xlsx:5
        --out output/20251109_115529/diversified.xlsx
    )
    exec "$PYBIN" -m src.feature_diversify.cli "${DEFAULT_ARGS[@]}"
else
    exec "$PYBIN" -m src.feature_diversify.cli "$@"
fi


