## Feature Spec: Run scripts for QB stacks and Game stacks

### Purpose
- Provide two convenience scripts to batch-generate stacked lineups and aggregate results into a single workbook for easy review.
- Keep compatibility with existing `run.sh` defaults and flags while introducing a new optional parameter for targeted game stacks.

### Existing context (as of today)
- `run.sh` exposes environment-driven parameters that map to CLI flags and writes two Excel workbooks by default:
  - `output/unfiltered_lineups.xlsx`
  - `output/filtered_lineups.xlsx`
- Each workbook contains a `Lineups` sheet with ranked lineups and metadata columns as described in `README.md`.
- Relevant current env vars: `LINEUPS`, `STACK`, `GAME_STACK`, `INCLUDE_PLAYERS`, `EXCLUDE_PLAYERS`, `OUT_UNFILTERED`, `OUT_FILTERED`, plus optional filters and solver knobs.

---

## Script A: `run_qb_stacks.sh`

### Goal
Generate the top N lineups for every quarterback in the projections pool (respecting all constraints/filters set in `run.sh`), then concatenate all `Lineups` into a single combined workbook so the top lineups containing each QB can be reviewed together.

### Inputs and configuration
- Inherit all parameters from `run.sh` via environment (e.g., `STACK`, `GAME_STACK`, filters, solver knobs). The script should not redefine defaults; it only sets `INCLUDE_PLAYERS` per QB during iteration.
- Primary control of how many lineups to generate per QB comes from `LINEUPS` (unchanged semantics). Example: if `LINEUPS=20`, generate up to 20 lineups for each QB.
- Optional new environment variables for this script:
  - `QB_STACKS_QB_LIST` (string, optional): comma-separated list of QB names to restrict the iteration. If empty, auto-discover all QBs from projections where `Position == QB`.
  - `QB_STACKS_KEEP_INTERMEDIATE` (bool-like: empty/0/false vs non-empty/1/true): keep the per-QB Excel outputs on disk. Default: keep.
  - `QB_STACKS_OUT_UNFILTERED` (path): aggregated output workbook for unfiltered lineups. Default: `output/qb_stacks_unfiltered.xlsx`.
  - `QB_STACKS_OUT_FILTERED` (path): aggregated output workbook for filtered lineups. Default: `output/qb_stacks_filtered.xlsx`.

### Behavior
1. Resolve the list of quarterbacks:
   - If `QB_STACKS_QB_LIST` is set, parse it.
   - Else, read the projections CSV specified by `PROJECTIONS` and extract unique `Name` values where `Position == 'QB'`.
   - Preserve a stable ordering (e.g., by descending projection, or alphabetical if projection missing). Default: alphabetical by name.
2. For each quarterback `q` in the list:
   - Set `INCLUDE_PLAYERS="q"` for the child run only (do not overwrite the caller’s environment permanently).
   - Clear any `EXCLUDE_PLAYERS` contamination specific to QB name formatting if needed (do not modify user-provided excludes otherwise).
   - Invoke `./run.sh` so all other parameters and filters apply as-is.
   - Capture the produced `OUT_UNFILTERED` and `OUT_FILTERED` paths for that run (use current env defaults if not overridden).
3. Aggregation:
   - Read each run’s `Lineups` sheet from the produced workbooks.
   - Add a new column `QB` with the quarterback’s name used for that run.
   - Concatenate all per-QB `Lineups` rows into a single DataFrame for unfiltered and (if present) filtered outputs separately.
   - Recompute `Rank` globally in descending `Projection` order (1..K) for each aggregated workbook.
   - Preserve all existing columns; do not drop or rename existing fields. Ensure `QB` is appended as a new column near other metadata fields (after `Game Stack`, before player slots is acceptable) while keeping column order consistent elsewhere.
   - Write the aggregated DataFrame to the `Lineups` sheet of `QB_STACKS_OUT_UNFILTERED` and `QB_STACKS_OUT_FILTERED`.
   - Optionally include a `Parameters` sheet summarizing high-level environment used (copied once from the first successful run) and a `Summary` sheet enumerating QBs processed and the number of feasible lineups per QB.
4. Exit code:
   - Return non-zero if no quarterbacks produced any feasible lineups; otherwise return zero.

### Output
- `output/qb_stacks_unfiltered.xlsx` and `output/qb_stacks_filtered.xlsx` by default, each with at least a `Lineups` sheet containing stacked results across all QBs.
- If `QB_STACKS_KEEP_INTERMEDIATE` is disabled, the per-QB intermediate workbooks may be deleted after aggregation (only if they are not the same as the aggregated outputs).

### Edge cases & rules
- If a given QB produces zero feasible lineups (due to constraints/filters), skip it and record that in the `Summary` sheet.
- If a filtered workbook is identical to unfiltered (i.e., no filters set), still produce both aggregated outputs for consistency.
- Names must match the projections `Name` exactly. The script should log skipped/missing names if any do not resolve to a QB.
- Avoid double-counting: each per-QB run should start from a clean state for `INCLUDE_PLAYERS`; do not accumulate includes across iterations.
- Performance: runs are sequential by default to keep logs readable. (Optional future: parallelization guarded by a `QB_STACKS_PARALLEL` flag.)

### Usage examples
```bash
# Use current run.sh defaults; 20 lineups per QB; aggregate
./agent/run_qb_stacks.sh

# Restrict to a subset of QBs
QB_STACKS_QB_LIST="Josh Allen,Patrick Mahomes" ./agent/run_qb_stacks.sh

# Change the aggregated outputs
QB_STACKS_OUT_UNFILTERED=output/custom_qb_unfiltered.xlsx \
QB_STACKS_OUT_FILTERED=output/custom_qb_filtered.xlsx \
./agent/run_qb_stacks.sh
```

### Acceptance criteria
- Running the script without additional env vars generates two aggregated workbooks with a `Lineups` sheet combining results for all detected QBs.
- The `Lineups` sheet includes a `QB` column indicating which QB was included for each lineup.
- Global ranks are recomputed and there are exactly `LINEUPS × (#QBs with feasible lineups)` rows unless some QBs are infeasible.
- All constraints and filters from `run.sh` are applied for each QB run.

---

## Script B: Game stack iterator `run_game_stacks.sh`

### Goal
For every distinct game (team vs opponent) present in the projections, generate the top N lineups that satisfy a game stack of size `GAME_STACK` targeted to that specific game. Aggregate the `Lineups` across all games into one workbook.

### New parameter required
- Introduce a targeted game parameter to `run.sh` and the CLI so the minimum game-stack count applies to a specific matchup rather than any game:
  - Environment variable: `GAME_STACK_TARGET` (string)
  - CLI flag: `--game-stack-target` (string)
- Expected format: normalized two-team key, case-insensitive, order-insensitive. Accept the following user inputs and normalize internally to `AAA/BBB` where `AAA < BBB` lexicographically:
  - `BUF/NYJ`, `NYJ/BUF`, `BUF@NYJ`, `NYJ@BUF`, `BUF-NYJ`, `NYJ-BUF`
- Semantics:
  - If `GAME_STACK > 0` and `GAME_STACK_TARGET` is set, enforce that at least `GAME_STACK` players selected in a lineup come from the specified game (combined across both teams) with all existing roster constraints.
  - If `GAME_STACK_TARGET` is not set, behavior is unchanged from today (the `game_stack` count may be satisfied by any game present in the lineup).

### Inputs and configuration
- Inherit all parameters from `run.sh` via environment.
- Use `LINEUPS` for how many lineups to generate per game.
- Optional new environment variables for this script:
  - `GAME_STACKS_GAME_LIST` (string, optional): comma-separated list of game keys to restrict iteration. Input forms may be as above; the script will normalize.
  - `GAME_STACKS_KEEP_INTERMEDIATE` (bool-like): keep or remove per-game workbooks. Default: keep.
  - `GAME_STACKS_OUT_UNFILTERED` (path): aggregated unfiltered output. Default: `output/game_stacks_unfiltered.xlsx`.
  - `GAME_STACKS_OUT_FILTERED` (path): aggregated filtered output. Default: `output/game_stacks_filtered.xlsx`.

### Behavior
1. Resolve the set of distinct games from the projections (based on `Team` and `Opponent` columns). Normalize to `AAA/BBB` with sorted team abbreviations to remove duplicates by order.
2. Validate `GAME_STACK > 0`. If zero, exit with an error explaining that targeted game stacks require a positive `GAME_STACK`.
3. For each game key `g` in the list:
   - Set `GAME_STACK_TARGET="g"` for the child run only.
   - Invoke `./run.sh` so all other parameters/filters apply.
   - Collect the produced `OUT_UNFILTERED` and `OUT_FILTERED` paths.
4. Aggregation (same rules as QB script):
   - Read each run’s `Lineups` sheet; add a `Game` column containing the normalized game key.
   - Concatenate rows; recompute global `Rank` by `Projection`.
   - Write `Lineups` to `GAME_STACKS_OUT_UNFILTERED` and `GAME_STACKS_OUT_FILTERED`.
   - Include a `Summary` sheet listing each game and the number of feasible lineups.

### Required code changes (separate implementation task)
- `run.sh`:
  - Add an env var default: `: "${GAME_STACK_TARGET:=}"`.
  - If set, append `--game-stack-target "$GAME_STACK_TARGET"` to `ARGS`.
- `src/cli.py`:
  - Add optional argument `--game-stack-target` (string, default `None`). Pass through to downstream layers.
- `src/models.py` (or equivalent config struct):
  - Add `game_stack_target: Optional[str]`.
- `src/optimizer.py`:
  - When `game_stack > 0` and `game_stack_target` is provided, build the game key for each player using sorted `(team, opponent)` and enforce the minimum count for that specific key. Otherwise, keep existing any-game behavior.
- `src/reporting.py` (no change required for aggregation if we aggregate post-run, but ensure existing `Lineups` column order is stable).

### Usage examples
```bash
# Iterate all games with GAME_STACK=3, aggregating results
GAME_STACK=3 ./agent/run_game_stacks.sh

# Restrict to two games, renaming aggregated outputs
GAME_STACKS_GAME_LIST="BUF/NYJ,KC/CIN" \
GAME_STACKS_OUT_UNFILTERED=output/custom_games_unfiltered.xlsx \
GAME_STACKS_OUT_FILTERED=output/custom_games_filtered.xlsx \
GAME_STACK=2 \
./agent/run_game_stacks.sh
```

### Acceptance criteria
- Running the script with `GAME_STACK>0` produces two aggregated workbooks with a `Lineups` sheet combining results for all detected games.
- The `Lineups` sheet includes a `Game` column containing the normalized matchup key.
- Global ranks are recomputed; row count equals `LINEUPS × (#games with feasible lineups)` unless infeasible cases occur.
- When `GAME_STACK_TARGET` is specified for a single manual run (outside the iterator), the optimizer enforces the stack size for that specific game only.

---

## Common implementation notes (non-binding)
- Aggregation may be implemented via a small Python helper (e.g., `pandas`) invoked by the scripts to read/concatenate/write Excel `Lineups`.
- Prefer not to overwrite the standard `OUT_UNFILTERED`/`OUT_FILTERED` files produced per run; instead, write separate aggregated outputs as specified above.
- Logging: print progress (which QB/game is being processed), counts of feasible lineups, and final aggregated counts.
- Idempotency: aggregated outputs are overwritten by default; add a `*_APPEND` flag later only if needed.
- Error handling: if no feasible lineups are produced for all iterations, return non-zero and emit an explanatory message.

## Out of scope for this spec
- Parallel execution mechanics, job scheduling, or caching of intermediate results.
- Changes to how exposures are calculated or additional aggregation tabs beyond what is specified.

