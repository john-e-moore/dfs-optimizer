## DFS Lineup Optimizer (DraftKings NFL)

This project builds optimal daily fantasy NFL lineups for the DraftKings Main Slate. It maximizes projected points while respecting roster rules, salary cap, and optional stacking constraints. It also supports lineup-level filtering and produces a clear Excel report with multiple tabs.

### What it does (in plain terms)
- Reads a CSV of player projections (name, team, position, salary, projection, ownership).
- Uses mathematical optimization to choose the best 9-player lineup:
  - 1 QB, 2 RB, 3 WR, 1 TE, 1 DST, and 1 FLEX (RB/WR/TE)
  - Total salary ≤ 50,000 and ≥ a minimum you control (default 45,000)
  - Optional “stacks”: pair your QB with teammates (WR/TE); optional “game stacks” ensure many players from the same game
  - Optional rule to disallow QB vs opposing DST
- Repeats the optimization to produce many unique lineups (by default up to 5,000; configurable)
- Optionally filters the lineups by ownership thresholds
- Exports an Excel workbook with Projections, Parameters, Lineups, and Players tabs

### How the optimization works (high-level)
We use a standard Mixed Integer Linear Programming (MILP) model via PuLP (CBC solver):
- For each player in the pool, we create a binary decision variable: 1 if selected, 0 otherwise
- Objective: maximize the sum of selected players’ `Projection`
- Constraints enforce:
  - Exactly 9 players per lineup
  - Position counts: `QB=1`, `DST=1`, `RB≥2`, `WR≥3`, `TE≥1` (FLEX makes up the rest)
  - Salary cap: total salary ≤ 50,000 and ≥ `min_salary`
  - Stacks: if QB is selected from a team, ensure at least N teammates at WR/TE from that same team
  - Game stacks: ensure at least K players from the same game (if enabled)
  - Optional: disallow selecting a QB and an opposing DST together
- To generate multiple unique lineups, we add a “no-duplicate” constraint each time: the new lineup must differ by at least one player from any previous lineup

This gives a precise, explainable solution with guarantees about constraints being satisfied.

### Data expectations
Input CSV (by default at `data/DraftKings NFL DFS Projections -- Main Slate.csv`) should include at least these columns:
- `Name`, `Team`, `Opponent`, `Position`, `Salary`, `Projection`, `Ownership`

Ownership can be in 0–1 or 0–100; it is normalized to 0–1 during loading.

### Outputs
Two Excel workbooks are produced by default:
- `output/unfiltered_lineups.xlsx`
- `output/filtered_lineups.xlsx` (only if filters are enabled; otherwise it mirrors unfiltered)

Each workbook contains:
- Projections: a copy of the input projections (cleaned/normalized)
- Parameters: a one-row table showing all parameters and filter values used
- Lineups: ranked in descending order of projection with these columns:
  - Rank
  - Projection
  - Salary (sum of lineup salaries)
  - Sum Ownership (integer percent, e.g., 156 means 1.56 total)
  - Product Ownership (scaled to a large integer for readability)
  - # Stacked (count of WR/TE stacked with the QB)
  - QB Stack (e.g., WR or TE,WR)
  - RB/DST Stack (True if lineup includes a DST and RB from the same team)
  - Game Stack (every game and count present in the lineup with counts ≥2, e.g., "CIN/CLE (4), ATL/TB (2)")
  - Player slots in order: QB, RB1, RB2, WR1, WR2, WR3, TE, FLEX, DST (formatted as `Player Name (TEAM)`)
- Players: exposure summary across all lineups:
  - Player (name only)
  - Position (from projections; never “FLEX”)
  - Team
  - # Lineups
  - % Lineups (rounded integer percent)

Additionally, JSON/CSV snapshots are written to `artifacts/` for debugging and visibility during development (cleaned projections, pools, lineups, parameters).

### Parameters and filters
- Core parameters:
  - lineup_count (default 5000)
  - min_salary (default 45000)
  - allow_qb_vs_dst (default False)
  - stack: number of WR/TE paired with the QB’s team (default 1)
  - game_stack: minimum players from the same game (default 0)
- Filters (optional, applied after generating lineups):
  - min_sum_projection (replaces min_player_projection)
  - min_sum_ownership, max_sum_ownership (on 0–1 scale before display)
  - min_product_ownership, max_product_ownership

### Performance knobs
- solver_threads: number of threads for CBC
- solver_time_limit_s: time limit in seconds for each solve

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run
Quick start with the included script (defaults set in the script):
```bash
./run.sh
```

Or call the CLI directly with flags:
```bash
python -m dfs_optimizer.cli \
  --projections "data/DraftKings NFL DFS Projections -- Main Slate.csv" \
  --lineups 5000 \
  --min-salary 45000 \
  --stack 1 \
  --game-stack 0 \
  --out-unfiltered output/unfiltered_lineups.xlsx \
  --out-filtered output/filtered_lineups.xlsx \
  # Optional filters:
  [--allow-qb-vs-dst] \
  [--min-sum-projection 120.0] \
  [--min-sum-ownership 0.9] [--max-sum-ownership 1.4] \
  [--min-product-ownership 1e-9] [--max-product-ownership 0.1] \
  # Optional performance:
  [--solver-threads 2] [--solver-time-limit-s 30]
```

Additional pruning/constraints flags:

```bash
  [--exclude-players "Player A,Player B"] \
  [--include-players "Player C"] \
  [--exclude-teams "BUF,CAR"] \
  [--min-team "CAR:3" --min-team "BUF:2"] \
  [--rb-dst-stack]
```

### Development quality
- Tests: run with `pytest` (unit tests and smoke tests)
- Sanity checks: inputs and model outputs are checked for validity
- Observability: intermediate artifacts saved in `artifacts/` for traceability

### Notes and limitations
- Projections and ownership quality drive results; this tool optimizes given the data
- Extremely tight/contradictory constraints (e.g., high min salary + strong stacks + restrictive filters) may yield few or no lineups
- The solver returns globally optimal lineups for the provided constraints; generating thousands of unique lineups can be time-consuming. Use `--solver-time-limit-s` and `--solver-threads` if needed

### Project structure
- `dfs_optimizer/`
  - `data_loader.py`: load, validate, and normalize projections
  - `models.py`: domain dataclasses and helpers
  - `optimizer.py`: MILP model and lineup generation
  - `filters.py`: lineup-level filters
  - `reporting.py`: Excel export and exposure summaries
  - `io_utils.py`, `logging_utils.py`, `observability.py`: utilities and snapshots
  - `cli.py`: command-line interface
- `tests/`: pytest suite covering all core modules
- `artifacts/`: intermediate snapshots
- `output/`: generated Excel workbooks
- `run.sh`: convenience script to run the pipeline

If you have questions or want to extend constraints (e.g., custom stacks, exposure caps), the code is organized to make that straightforward—start with `models.py` and `optimizer.py`.
