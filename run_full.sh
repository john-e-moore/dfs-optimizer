#!/usr/bin/env bash
set -euo pipefail

# NFL $100k Power Sweep (740, 15% 1st)
# NFL $100 Double Spy (555, 20% 1st)
# NFL $50k Spy (555, 10% 1st)
# NFL $30k Spy (334, 17% 1st)
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 21 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 21 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 24 --min-salary 49600 --game-stack 5

# NFL $400k Spy (4444, 25% 1st)
# NFL $500k Power Sweep (3703, 20% 1st)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 17 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 1 --bringback --max-weighted-ownership 17 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 19 --min-salary 49600 --game-stack 5

# NFL $200k Power Sweep (1481, 25% 1st)
# NFL $150k Spy (1666, 17% 1st)
bash run.sh --ss --lineups 250 --stack 1 --max-weighted-ownership 19 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --max-weighted-ownership 19 --min-salary 49600
bash run.sh --ss --lineups 250 --stack 2 --bringback --max-weighted-ownership 19 --min-salary 49600
