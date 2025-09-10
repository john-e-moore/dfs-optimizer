## Mini Spec: DFS Lineup Optimizer

### Objective
Build a lineup optimizer for DraftKings NFL Main Slate that maximizes total projected points from the input projections CSV at `data/DraftKings NFL DFS Projections -- Main Slate.csv`.

### Lineup Structure & Constraints
- Positions: 1 QB, 2 RB, 3 WR, 1 TE, 1 DST, 1 FLEX (FLEX ∈ {RB, WR, TE}).
- Salary cap: total salary ≤ 50000; enforce minimum salary ≥ 45000 (user-configurable min).
- Optimization target: maximize sum of player `Projection`.
- Count of lineups: user-configurable; default 5000.
- Allow QB vs. opposing DST: configurable (default False).
- Stack: number of WR/TE paired with QB from same team; default 1.
- Game stack: minimum number of players from the same game; default 0.

### Filters (Optional)
- Minimum projection per player.
- Maximum/Minimum sum ownership across lineup.
- Maximum/Minimum product ownership across lineup.

### Output
- Excel workbook outputs:
  - `output/unfiltered_lineups.xlsx`: all optimized lineups, unfiltered.
  - `output/filtered_lineups.xlsx`: lineups after applying enabled filters.
- Workbook tabs:
  - `Projections`: copy of input projections.
  - `Parameters`: values used for this optimization run.
  - `Lineups`: ranked lineups (descending projection):
    - Columns: Rank, Projection, Sum Ownership, Product Ownership (human-readable scaled), Stack (positions paired with QB), Game Stack (max players from same game), followed by player columns in order: QB, RB, RB, WR, WR, WR, TE, FLEX, DST with names formatted like `Player Name (TEAM)`.

### Data Expectations
- Input CSV includes at least: `Name`, `Team`, `Opponent`, `Position`, `Salary`, `Projection`, `Ownership`.

### Implementation Notes
- Use Python with numpy/pandas/scikit-learn ecosystem.
- Use classes/dataclasses to encapsulate data loading, constraints, optimization, filtering, and exporting.
- Use descriptive, verbose variable names; clean, well-commented, readable code.
- Write intermediate artifacts to `output/` at each transformation step for observability.

### Testing
- Use pytest for unit and smoke tests.
- Cover data loading/validation, constraint construction, filters, export formatting, CLI params, and uniqueness of generated lineups.
- Include a small synthetic dataset to assert roster rules, stacks, and game stacks.
- Optional: add coverage reporting.

### Runtime Sanity Checks
- Validate input parameters (e.g., lineup count > 0, 0 ≤ min_salary ≤ 50000, stack/game_stack ≥ 0).
- Validate player rows on load: positions in {QB, RB, WR, TE, DST}, Salary ≥ 0, Projection ≥ 0, Ownership in [0,1] or [0,100] with normalization.
- Assert lineup feasibility after solve: required positions, salary within [min_salary, 50000], stack and game stack constraints when enabled, and no duplicate players.
- Guard against empty results and log reasons when constraints are infeasible.
