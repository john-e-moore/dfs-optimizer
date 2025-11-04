#!/usr/bin/env bash
set -euo pipefail

# Wrapper for diversified lineup selection (Jaccard). Pass-through to Python CLI.

# Prefer venv python if available
if [[ -x "venv/bin/python" ]]; then
    PYBIN="venv/bin/python"
else
    PYBIN="python"
fi

exec "$PYBIN" -m src.feature_diversify.cli "$@"


