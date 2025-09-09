### Feature: Constraints Enhancements — Work Plan

Scope: Implement new constraints and modify existing filters per `agent/feature-constraints/spec.md` for the DFS optimizer. Ensure CLI, core optimization, filters, reporting, tests, and docs are updated.

### Requirements (from spec)
- Change: Replace `min_player_projection` with `min_sum_projection` (minimum lineup projection).
- Pruning: Exclude specific players by name (single or list).
- Pruning: Include specific players who must be in all lineups.
- Pruning: Exclude teams (single or list) from the player pool.
- Constraint: Minimum number of players by team (e.g., `CAR: 3`).
- Constraint: RB/DST stack — if enabled, each lineup must have an RB on the same team as the DST.

### Design Decisions
- Parameterization lives in `models.Params` and CLI flags in `cli.py`.
- Exclusions/requirements applied at the MILP level in `optimizer.py` (not only pre-pruning), to keep guarantees when generating many unique lineups.
- Keep `filters.py` for post-solve lineup filtering (e.g., `min_sum_projection`).
- Maintain backward-compat for `--min-player-projection` by accepting it as an alias with a deprecation warning in `cli.py`.

### CLI/Config Additions
- `--exclude-players` (repeatable or comma-separated): names matching `Name` in projections.
- `--include-players` (repeatable or comma-separated): names that must be selected in every lineup.
- `--exclude-teams` (repeatable or comma-separated): team abbreviations.
- `--min-team PLAYERS` (repeatable): format `TEAM:COUNT` (e.g., `CAR:3`).
- `--rb-dst-stack` (flag): enable RB/DST same-team stack.
- Replace `--min-player-projection` with `--min-sum-projection FLOAT`.
  - Accept old flag as alias; warn and map to new.

### Data Model Changes (`dfs_optimizer/models.py`)
- Extend `Params`:
  - `excluded_players: set[str] = field(default_factory=set)`
  - `included_players: set[str] = field(default_factory=set)`
  - `excluded_teams: set[str] = field(default_factory=set)`
  - `min_players_by_team: dict[str, int] = field(default_factory=dict)`
  - `rb_dst_stack: bool = False`
  - Move/rename filter field: `min_sum_projection: float | None = None`
- Optional: keep legacy `min_player_projection` only in CLI parsing layer; do not persist in `Params`.

### Validation (`dfs_optimizer/data_loader.py` or a new `validation.py`)
- Normalize player names and team codes.
- Error if any `included_players` not present in the pool after exclusions.
- Error if `included_players` size exceeds feasible roster capacity (e.g., >9 or position-infeasible).
- Error if `min_players_by_team` implies infeasibility (e.g., sum of mins > 9; or mins violate position caps).
- Warning if `exclude-teams` remove all DSTs or all QBs.

### Optimizer Changes (`dfs_optimizer/optimizer.py`)
- Exclude players: for any player p in `excluded_players`, force `x_p = 0`.
- Exclude teams: for any player p with team in `excluded_teams`, force `x_p = 0`.
- Include players: for any player p in `included_players`, force `x_p = 1`.
- Min players by team: for each team t in `min_players_by_team`, add `sum_{p in team t} x_p ≥ min_t`.
- RB/DST stack:
  - For each team t: `x_dst_t ≤ sum_{rb in team t} x_rb` ensures a same-team RB if that DST is chosen.
  - Keep existing single-DST constraint intact.
- Ensure uniqueness constraints remain compatible (they will, since they operate on `x` variables per lineup).

### Filters Changes (`dfs_optimizer/filters.py`)
- Remove handling of `min_player_projection`.
- Add lineup-level filter: keep lineup if `sum(projection) ≥ min_sum_projection` when provided.

### Reporting (`dfs_optimizer/reporting.py`)
- Confirm RB/DST stack column computation aligns with the new optimizer semantics.
- Update Parameters tab to include new params: excluded/included players, excluded teams, team mins, rb_dst_stack, min_sum_projection.

### CLI Parsing (`dfs_optimizer/cli.py`)
- Add new flags with parsing for repeatable/comma-separated values.
- Implement `TEAM:COUNT` parsing for `--min-team` (allow multiple occurrences).
- Map old `--min-player-projection` to `min_sum_projection` with a deprecation warning to stderr/log.
- Update help text and README sync.

### Run Script (`run.sh`)
- Expose new flags with sane defaults/examples; keep current defaults unchanged unless specified.

### Tests (`tests/`)
- Unit tests for optimizer constraints:
  - Exclude players: ensure none appear in any lineup.
  - Include players: ensure all lineups include specified players (single and multiple).
  - Exclude teams: ensure no players from those teams appear.
  - Min players by team: ensure threshold is met for at least two different teams.
  - RB/DST stack: ensure if a DST is selected, at least one RB of same team is present.
- Filter tests:
  - `min_sum_projection` correctly filters below-threshold lineups.
- CLI parsing tests:
  - Comma-separated and repeatable formats.
  - `TEAM:COUNT` parsing and error cases.
  - Deprecation path for `--min-player-projection`.

### Acceptance Criteria
- New CLI flags function as documented; old `--min-player-projection` continues to work with a warning.
- All constraints enforce correctly across every generated lineup.
- Tests cover new functionality and pass in CI.
- README and `run.sh` reflect new options.
- Snapshots/artifacts include new params for traceability.

### Migration/Docs
- Update `README.md` sections:
  - Replace references to `min_player_projection` with `min_sum_projection`.
  - Document new flags with examples.
  - Note deprecation policy for one release, then remove old flag.

### Performance & Risks
- Added constraints may slightly increase solver time; provide guidance in README to adjust `--solver-threads` and `--solver-time-limit-s` if needed.
- Risk of infeasible parameter combinations; mitigated with upfront validation and clear error messages.

### Implementation Steps (ordered)
1) Extend `models.Params` and add parsing helpers for lists and `TEAM:COUNT`.
2) Implement CLI flags, parsing, and deprecation mapping.
3) Add validations and normalization during data loading/param preparation.
4) Implement optimizer constraints (exclude/include, teams, team mins, RB/DST stack).
5) Implement `min_sum_projection` in filters; remove old projection-per-player filter usage.
6) Update reporting to surface new params and ensure RB/DST stack column alignment.
7) Update `run.sh` and `README.md` usage examples.
8) Add tests for CLI, optimizer, and filters; run `pytest` and fix issues.
9) Final pass on logs/observability and artifacts snapshots.

### Out-of-Scope (explicitly not included now)
- Exposure caps and diversification beyond existing uniqueness constraint.
- Complex stacking (e.g., secondary stacks beyond RB/DST already in scope).


