## DFS Lineup Optimizer (DraftKings NFL)

This project builds optimal daily fantasy NFL lineups for the DraftKings Main Slate. It maximizes projected points while respecting roster rules, salary cap, and optional stacking constraints. Constraints like ownership bounds are enforced during optimization, and a clear Excel report is produced with multiple tabs.

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
By default, outputs are written under a timestamped subfolder, e.g., `output/20250910_142535/`:
- `output/<timestamp>/lineups.xlsx`
- `output/<timestamp>/lineups.json`
- `output/<timestamp>/parameters.json`

Each workbook contains:
- Projections: a copy of the input projections (cleaned/normalized)
- Parameters: two-column table (one parameter per row): Column A = Parameter, Column B = Value
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

Additionally, CSV/JSON snapshots are written alongside the Excel files in the same timestamped run directory for traceability:
- `cleaned_projections.csv`, `players_pool.csv`

### Parameters and constraints
- Core parameters:
  - lineup_count (default 5000)
  - min_salary (default 45000)
  - allow_qb_vs_dst (default False)
  - stack: number of WR/TE paired with the QB’s team (default 1)
  - game_stack: minimum players from the same game (default 0)
  - game_stack_target: specific matchup to satisfy when game_stack > 0 (normalized `AAA/BBB`; default unset)
- Constraints (enforced during optimization):
  - min_sum_projection (minimum total lineup projection)
  - min_sum_ownership, max_sum_ownership (ownership sum bounds on 0–1 scale)
  - min_product_ownership, max_product_ownership (implemented via log transform)

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
python -m src.cli \
  --projections "data/DraftKings NFL DFS Projections -- Main Slate.csv" \
  --lineups 5000 \
  --min-salary 45000 \
  --stack 1 \
  --game-stack 0 \
  # Optional targeted game constraint (order-insensitive, normalized to AAA/BBB):
  [--game-stack-target "BUF/NYJ"] \
  --outdir output \
  # Optional constraints:
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
- `src/`
  - `data_loader.py`: load, validate, and normalize projections
  - `models.py`: domain dataclasses and helpers
  - `optimizer.py`: MILP model and lineup generation
  - `filters.py`: legacy post-generation filters (kept for reference); constraints are now enforced during optimization
  - `reporting.py`: Excel export and exposure summaries
  - `io_utils.py`, `logging_utils.py`, `observability.py`: utilities and snapshots
  - `cli.py`: command-line interface
- `tests/`: pytest suite covering all core modules
- `artifacts/`: intermediate snapshots
- `output/`: generated Excel workbooks
- `run.sh`: convenience script to run the pipeline

If you have questions or want to extend constraints (e.g., custom stacks, exposure caps), the code is organized to make that straightforward—start with `models.py` and `optimizer.py`.

### Examples: common run configurations

Below are copy-pasteable examples for typical strategies. Use either the CLI form or the `./run.sh` form (env vars override script defaults).

- **Basic run (no special stacks)**
  - CLI:
    ```bash
    python -m src.cli --lineups 500 --min-salary 49000 --stack 1 --game-stack 0
    ```
  - Script (writes to `output/<timestamp>/...`):
    ```bash
    LINEUPS=500 MIN_SALARY=49000 STACK=1 GAME_STACK=0 ./run.sh
    ```

- **QB stacking (pair QB with teammates WR/TE)**
  - Increase the number of teammates required with `--stack`:
    ```bash
    # Require QB + 2 pass-catchers (WR/TE)
    python -m src.cli --stack 2 --lineups 1000
    ```
  - Script equivalent:
    ```bash
    STACK=2 LINEUPS=1000 ./run.sh
    ```

- **RB/DST stacking (RB from same team as chosen DST)**
  - CLI:
    ```bash
    python -m src.cli --rb-dst-stack --lineups 1000
    ```
  - Script:
    ```bash
    RB_DST_STACK=1 LINEUPS=1000 ./run.sh
    ```

- **Game stacking (minimum players from the same game)**
  - Set a global minimum per lineup with `--game-stack`:
    ```bash
    # At least 4 total players from the same game
    python -m src.cli --game-stack 4 --lineups 800
    ```
  - Script:
    ```bash
    GAME_STACK=4 LINEUPS=800 ./run.sh
    ```

- **Targeted game stack (focus a specific matchup)**
  - CLI accepts `TEAM1/TEAM2`, `TEAM1-TEAM2`, or `TEAM1@TEAM2` (order-insensitive):
    ```bash
    python -m src.cli --game-stack 5 --game-stack-target "BUF/NYJ" --lineups 600
    ```
  - Script:
    ```bash
    GAME_STACK=5 GAME_STACK_TARGET="BUF/NYJ" LINEUPS=600 ./run.sh
    ```

- **Prevent QB vs opposing DST**
  - CLI:
    ```bash
    python -m src.cli --stack 2 --allow-qb-vs-dst  # omit flag to disallow
    ```
  - Script:
    ```bash
    ALLOW_QB_VS_DST=1 STACK=2 ./run.sh   # leave unset to disallow
    ```

- **Ownership filters (post-generation filtering)**
  - CLI:
    ```bash
    python -m src.cli \
      --min-sum-ownership 0.80 \
      --max-sum-ownership 1.40 \
      --min-product-ownership 1e-9 \
      --max-product-ownership 1e-1
    ```
  - Script:
    ```bash
    MIN_SUM_OWNERSHIP=0.80 MAX_SUM_OWNERSHIP=1.40 \
    MIN_PRODUCT_OWNERSHIP=1e-9 MAX_PRODUCT_OWNERSHIP=1e-1 \
    ./run.sh
    ```

- **Include/exclude players and teams; team minimums**
  - CLI:
    ```bash
    python -m src.cli \
      --include-players "Josh Allen" \
      --exclude-players "Player A,Player B" \
      --exclude-teams "CAR,NE" \
      --min-team "BUF:3" --min-team "NYJ:2"
    ```
  - Script:
    ```bash
    INCLUDE_PLAYERS="Josh Allen" \
    EXCLUDE_PLAYERS="Player A,Player B" \
    EXCLUDE_TEAMS="CAR,NE" \
    MIN_TEAM="BUF:3,NYJ:2" \
    ./run.sh
    ```

- **Performance knobs**
  - CLI:
    ```bash
    python -m src.cli --solver-threads 4 --solver-time-limit-s 30 --lineups 2000
    ```
  - Script:
    ```bash
    SOLVER_THREADS=4 SOLVER_TIME_LIMIT_S=30 LINEUPS=2000 ./run.sh
    ```

### Helper scripts: stacking workflows

- **QB stacking across all quarterbacks: `./run_qb_stacks.sh`**
  - What it does: runs `./run.sh` once per QB discovered in the projections (or a provided list), then aggregates all outputs into two Excel files with a `QB` column.
  - Default outputs: `output/<timestamp>/qb_stacks_unfiltered.xlsx` and `output/<timestamp>/qb_stacks_filtered.xlsx`.
  - Examples:
    ```bash
    # Run for all QBs in the projections
    ./run_qb_stacks.sh

    # Run for a specific set of QBs
    QB_STACKS_QB_LIST="Josh Allen, Jalen Hurts, Patrick Mahomes" ./run_qb_stacks.sh

    # Use a custom projections file and keep intermediates cleaned up
    PROJECTIONS="/path/to/my.csv" QB_STACKS_KEEP_INTERMEDIATE=0 ./run_qb_stacks.sh
    ```

- **Game stacking across all games: `./run_game_stacks.sh`**
  - What it does: discovers all matchups from projections (or uses a provided list), runs `./run.sh` per game with a targeted game stack, then aggregates outputs with a `Game` column.
  - Default outputs: `output/<timestamp>/game_stacks_unfiltered.xlsx` and `output/<timestamp>/game_stacks_filtered.xlsx`.
  - Notes:
    - If you explicitly set `GAME_STACK`, it must be > 0 for this script.
    - Game keys are normalized; any of `AAA/BBB`, `AAA@BBB`, or `AAA-BBB` is accepted (order-insensitive).
  - Examples:
    ```bash
    # Run for all games discovered in projections (uses script defaults; run.sh defaults to GAME_STACK=0)
    ./run_game_stacks.sh

    # Run for a specific set of games with a 4-player minimum per targeted game
    GAME_STACKS_GAME_LIST="BUF/NYJ, DAL-PHI" GAME_STACK=4 ./run_game_stacks.sh

    # Custom projections and remove intermediates after aggregation
    PROJECTIONS="/path/to/my.csv" GAME_STACKS_KEEP_INTERMEDIATE=0 ./run_game_stacks.sh
    ```

### Script logs and exit codes

- `./run_qb_stacks.sh` and `./run_game_stacks.sh` write detailed logs to the timestamped run directory:
  - `output/<timestamp>/run_qb_stacks.log`
  - `output/<timestamp>/run_game_stacks.log`
- Each script prints per-entity counts from the aggregated `Summary` sheet and totals for both unfiltered and filtered outputs.
- Exit codes:
  - 0 if at least one lineup was aggregated across all iterations
  - 1 if no feasible lineups were found (useful for CI or checks)

### Tips
- `./run.sh` sets opinionated defaults (e.g., higher `MIN_SALARY`; `GAME_STACK` defaults to 0). Override via env vars as shown above if desired.
- When using default output names, both the CLI and scripts will place results under `output/<timestamp>/` automatically.
