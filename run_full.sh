#!/usr/bin/env bash
set -euo pipefail

# Small (<1k)
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 23 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 23 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 24 --min-salary 49600 --game-stack 5

# Medium (1-3k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 21 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 21 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 22 --min-salary 49600

# Large (3k-5k)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 19 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 1 --bringback --max-weighted-ownership 19 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 20 --min-salary 49600 --game-stack 5


