## Work Plan: Run scripts for QB stacks and Game stacks

### Objectives
- Add two convenience scripts to iterate stacked runs and aggregate results:
  - `run_qb_stacks.sh`: iterate every QB, run with `INCLUDE_PLAYERS="<QB>"`, aggregate `Lineups`.
  - `run_game_stacks.sh`: iterate every game, run with targeted game stacks, aggregate `Lineups`.
- Introduce targeted game-stack parameter to support per-game stacking: `GAME_STACK_TARGET` (`--game-stack-target`).

### Deliverables
- Scripts:
  - `agent/run_qb_stacks.sh`
  - `agent/run_game_stacks.sh`
- New CLI/env parameter wired through the stack:
  - `GAME_STACK_TARGET` env + `--game-stack-target` CLI
- Aggregation helper (Python) used by both scripts to read per-run workbooks and write combined outputs.
- Documentation updates in `README.md` (flags, usage examples).
- Tests covering targeted game stacks and basic script smoke paths.

### Assumptions
- Projections CSV includes at least: `Name`, `Team`, `Opponent`, `Position`, `Projection`.
- Existing `Lineups` sheet schema remains stable as described in `README.md`.
- Aggregation operates post-run (read produced Excel; no change to current report writer needed).

---

## Milestones & Steps

### M1: Targeted game-stack parameter
1) `run.sh`
   - Add env default: `: "${GAME_STACK_TARGET:=}"`.
   - If set, append `--game-stack-target "$GAME_STACK_TARGET"` to `ARGS`.
2) `src/cli.py`
   - Add optional `--game-stack-target` (string, default None); pass into config.
3) `src/models.py` (or config module)
   - Add field `game_stack_target: Optional[str]` to the configuration struct.
4) `src/optimizer.py`
   - If `game_stack > 0` and `game_stack_target` set:
     - Build normalized game key for each player as `AAA/BBB` with sorted team codes.
     - Enforce at least `game_stack` selected players where player’s game key equals the target.
   - Else keep existing any-game behavior.
5) Tests
   - Unit: given small slate, verify that targeted game constraint binds only the specified game.
   - Negative: with conflicting filters, expect zero feasible lineups.

Acceptance for M1: Running CLI with `--game-stack-target BUF/NYJ --game-stack 3` yields lineups with ≥3 players from BUF/NYJ only; behavior unchanged when target not set.

### M2: Aggregation helper (shared)
1) Create `tools/aggregate_lineups.py` (top-level):
   - Inputs: list of Excel paths, output path, sheet name `Lineups`, extra column name/value pair (e.g., `QB`, `Game`).
   - Behavior:
     - Read each `Lineups` sheet via pandas.
     - Add extra column (constant per input file).
     - Concatenate; sort by `Projection` desc; recompute `Rank` 1..K.
     - Preserve existing columns; append the new column near metadata (after `Game Stack`).
     - Write to output workbook `Lineups` sheet. Optionally include `Summary` and `Parameters` sheets if provided.
2) Minimal CLI for the helper so bash scripts can call it cleanly.

Acceptance for M2: Given two small `Lineups` files, outputs a combined workbook with correct ranks and added column.

### M3: `run_qb_stacks.sh`
1) Inputs & env defaults
   - Respect all `run.sh` envs; do not override defaults globally.
   - New (script-scoped) envs with defaults:
     - `QB_STACKS_QB_LIST` (empty → auto-discover from projections)
     - `QB_STACKS_OUT_UNFILTERED=output/qb_stacks_unfiltered.xlsx`
     - `QB_STACKS_OUT_FILTERED=output/qb_stacks_filtered.xlsx`
     - `QB_STACKS_KEEP_INTERMEDIATE=true`
2) Discover QB list
   - If `QB_STACKS_QB_LIST` set → parse.
   - Else parse `PROJECTIONS` CSV for `Position == 'QB'`; alphabetical by `Name`.
3) Iterate
   - For each QB `q`: run `./run.sh` with `INCLUDE_PLAYERS="q"` (scoped to that invocation).
   - Capture per-run `OUT_UNFILTERED`/`OUT_FILTERED` paths (use env or defaults).
4) Aggregate
   - Call aggregation helper twice (unfiltered/filtered) adding column `QB=q`.
   - Recompute global `Rank`; write combined outputs to `QB_STACKS_OUT_*`.
   - Optional `Summary` tab with feasible counts per QB.
5) Cleanup
   - If `QB_STACKS_KEEP_INTERMEDIATE` is false, remove per-QB workbooks if distinct from aggregated outputs.

Acceptance for M3: Running script produces aggregated `Lineups` with `QB` column; logs infeasible QBs; exits 0 if any feasible lineups exist.

### M4: `run_game_stacks.sh`
1) Inputs & env defaults
   - Requires `GAME_STACK > 0`; exit with helpful error otherwise.
   - New envs:
     - `GAME_STACKS_GAME_LIST` (empty → auto-discover from projections)
     - `GAME_STACKS_OUT_UNFILTERED=output/game_stacks_unfiltered.xlsx`
     - `GAME_STACKS_OUT_FILTERED=output/game_stacks_filtered.xlsx`
     - `GAME_STACKS_KEEP_INTERMEDIATE=true`
2) Discover games
   - From projections, derive unique normalized keys `AAA/BBB` (sorted team codes) using `Team` and `Opponent`.
   - If `GAME_STACKS_GAME_LIST` provided, normalize each input key to the same form and restrict.
3) Iterate
   - For each game `g`: run `./run.sh` with `GAME_STACK_TARGET=g`.
   - Capture per-run outputs.
4) Aggregate
   - Use helper to combine `Lineups`, adding `Game=g` column; recompute global `Rank`.
   - Write to `GAME_STACKS_OUT_*`; add `Summary` tab with feasible counts per game.
5) Cleanup per `GAME_STACKS_KEEP_INTERMEDIATE`.

Acceptance for M4: Script iterates all games and produces aggregated outputs with `Game` column; targeted stacks enforced per run.

### M5: Documentation & polish
1) `README.md`
   - Document `--game-stack-target` and `GAME_STACK_TARGET`.
   - Add usage for both scripts with examples.
2) Logging and UX
   - Log which QB/game is running, counts found, final totals.
   - Non-zero exit if no feasible lineups across all iterations.

---

## Testing Plan
- Unit tests
  - Optimizer: targeted game constraint selects only specified matchup.
- Integration/smoke
  - Tiny projections fixture with 2 QBs and 2 games to verify both iterators and aggregation.
  - Verify aggregated `Lineups` row counts: ≈ `LINEUPS × feasible_entities` and global ranks monotonic.
- CLI/flag parsing
  - `--game-stack-target` passed through and reflected in config.

## Performance & Reliability
- Sequential runs by default to keep logs clear and avoid solver contention.
- Consider `QB_STACKS_PARALLEL`/`GAME_STACKS_PARALLEL` later if needed.
- Defensive checks for missing sheets/files; continue aggregation with remaining runs.

## Risks & Mitigations
- Name mismatches for QBs → log and skip; surface in `Summary`.
- Duplicate/ambiguous team codes → rely on projections’ `Team`/`Opponent`; document normalization.
- Filters causing widespread infeasibility → clearly report counts and exit code.

## Timeline (rough)
- M1: 0.5–1 day
- M2: 0.5 day
- M3: 0.5 day
- M4: 0.5 day
- M5: 0.5 day

## Out of Scope
- Parallel execution, caching, or advanced exposure controls.
- Changes to existing report column ordering beyond appending `QB`/`Game` and recomputing `Rank`.

