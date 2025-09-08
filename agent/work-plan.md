## Work Plan: DFS Lineup Optimizer

### 1) Project Setup
- Initialize Python environment and dependencies (numpy, pandas, scikit-learn, openpyxl/xlsxwriter, pulp or OR-Tools, pytest, pytest-cov).
- Create `output/` artifacts structure and helper logging/IO utilities.

### 2) Data Layer
- Implement loader to read `data/DraftKings NFL DFS Projections -- Main Slate.csv` into DataFrame.
- Validate required columns: Name, Team, Opponent, Position, Salary, Projection, Ownership.
- Normalize/clean positions, teams, numeric types; persist cleaned CSV to `output/cleaned_projections.csv`.

### 3) Domain Models
- Define dataclasses:
  - Player: identity, team, opponent, position, salary, projection, ownership.
  - Parameters: lineup count, min salary, allow_qb_vs_dst, stack, game_stack, filter thresholds.
- Add helpers to compute game key (e.g., `sorted([Team, Opponent]).join('-')`).

### 4) Optimization Engine
- Choose solver: MILP with PuLP or OR-Tools. Decision vars per player-position slot.
- Objective: maximize sum of `Projection` for chosen players.
- Constraints per lineup:
  - Roster counts: 1 QB, 2 RB, 3 WR, 1 TE, 1 DST, 1 FLEX (FLEX ∈ {RB, WR, TE}).
  - Salary cap ≤ 50000 and salary floor ≥ min_salary.
  - No duplicate players across slots; binary selection per player.
  - Optional: disallow QB vs opposing DST when flag is False.
  - Stack: ensure at least N WR/TE from QB team.
  - Game stack: ensure at least K players from same game.
- Generate N unique lineups (default 5000) via iterative solver with no-duplicate constraints.
- Save unfiltered results to `output/unfiltered_lineups.xlsx`.

### 5) Filters
- Implement lineup-level filters:
  - Min per-player projection (drop lineups containing players below threshold).
  - Sum ownership min/max.
  - Product ownership min/max (store human-readable scaled value as well).
- Apply filters to unfiltered lineups and save to `output/filtered_lineups.xlsx`.

### 6) Reporting/Export
- Create Excel writer with tabs:
  - Projections: cleaned projections DataFrame.
  - Parameters: parameters DataFrame (single row with values used).
  - Lineups: ranked by projection, with required columns and player order (QB, RB, RB, WR, WR, WR, TE, FLEX, DST) and `Name (TEAM)` formatting.

### 7) CLI / Config Interface
- Provide CLI with arguments for parameters and filters; sensible defaults from spec.
- Validate inputs and echo effective parameters to console and `Parameters` tab.

### 8) Observability
- Write intermediate artifacts: cleaned projections, solver summaries, lineup JSON/CSV snapshots.
- Add basic timing and counts; log reasons for filtered-out lineups.

### 9) QA & Testing
- Test stack with pytest:
  - Data loading/validation (required columns, type normalization, ownership normalization to [0,1]).
  - Constraint builders (roster counts, salary bounds, no QB vs DST when disabled, stack and game stack).
  - Filters (min per-player projection, sum/product ownership bounds) and correct exclusion reasons.
  - Export formatting (tabs present, columns order and labels, `Name (TEAM)` formatting).
  - CLI parameters parsing and defaults.
  - Uniqueness of generated lineups across N iterations.
- Add small synthetic dataset fixtures for deterministic tests.
- Smoke test end-to-end generating ~10 lineups and writing workbooks.
- Optional: add `pytest-cov` with a modest threshold for core modules.

### 10) Performance & Scale
- Optimize solver warm starts and constraint reuse across lineups.
- Parallelize lineup generation batches when feasible.
- Cache parsed data and precomputed player groups (by team, by game).

### 11) Runtime Sanity Checks (in code)
- Validate input params on start: lineup_count > 0, 0 ≤ min_salary ≤ 50000, stack ≥ 0, game_stack ≥ 0.
- On data load: assert allowed positions, non-negative salary/projection, bounded ownership (normalize if given as percent).
- After each lineup: assert roster counts, salary bounds, no duplicates, constraints satisfied (stack/game stack/QB vs DST when applicable).
- On infeasible solve or zero lineups: raise clear error with diagnostic context and suggestions.
