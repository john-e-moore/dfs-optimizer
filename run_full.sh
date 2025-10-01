#!/usr/bin/env bash
set -euo pipefail

# Flat small (<1k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 20 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 19 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 19 --min-salary 49600
# Flat mid (1-3k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 18 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 17 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 17 --min-salary 49600
# Flat large (>3k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 16 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 15 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 15 --min-salary 49600

# Top-heavy small (<1k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 18 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 17 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 17 --min-salary 49600
# Top-heavy mid (1-3k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 17 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 16 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 16 --min-salary 49600
# Top-heavy large (>3k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 16 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 15 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 15 --min-salary 49600
