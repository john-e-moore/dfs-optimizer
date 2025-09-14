## Work Plan — Constraints v2 Implementation

### Guiding Principles
- **Iterative delivery** with sanity checks after each milestone.
- Replace post-run filters with **hard optimizer constraints**.
- Produce a single set of outputs: `lineups.json` and `lineups.xlsx` per run directory.

### 0) Baseline and Discovery (sanity check)
- Run current flow to establish baseline outputs and behavior.
  - Command: `python -m src.cli --lineups 100` (adjust projections path if needed)
  - Note locations where unfiltered/filtered outputs and snapshots are written.
- Capture a minimal test slate (e.g., 40–80 players) to speed iteration.

### 1) Parameter and CLI preparation
- `src/cli.py`:
  - Remove `--out-unfiltered` and `--out-filtered` flags. Add `--outdir` (default `output/`) for where to place timestamped outputs.
  - Remove `--min-player-projection` and its deprecation mapping code.
  - Normalize ownership inputs as currently done; keep `--min-sum-projection`, `--min/max-sum-ownership`, `--min/max-product-ownership`.
- `src/models.py` (`Parameters`):
  - Ensure fields exist for all constraint knobs from spec. Remove `min_player_projection` if present.
  - Add validation:
    - Ownership/product thresholds in [0,1]; projection thresholds ≥ 0; min ≤ max.
- Sanity check: run CLI `--help`; run with no flags to ensure startup OK.

### 2) Output model consolidation
- Single run directory: keep current timestamped folder logic, but simplify naming.
- Write only:
  - `lineups.json` and `lineups.xlsx` (final, constraint-compliant lineups)
  - Keep snapshots for projections, player pool, parameters as-is.
- `src/cli.py`:
  - Remove post-filter branch and duplicate exports.
  - Call `snapshot_lineups` once to `lineups.json` with final lineups.
  - Update timing/logging to reflect single count (no “Filtered/Dropped”).
- Sanity check: run and confirm only `lineups.json` and `lineups.xlsx` exist in the run dir.

### 3) Remove post-run filters and shift to constraints
- Delete usage of `src/filters.py` from the runtime path.
- If `filters.py` provides reusable predicates, either migrate small helpers inline to `optimizer` or remove file entirely if unused.
- Sanity check: code compiles and runs without importing `filters`.

### 4) Implement optimization-time constraints
- `src/optimizer.py`:
  - Enforce Projection Sum: Σ P(i∈L) ≥ `min_sum_projection` when provided.
  - Enforce Ownership Sum bounds: Σ O(i∈L) ≥ min and/or ≤ max.
  - Enforce Ownership Product bounds using log transform (preferred):
    - Define ε = 1e-6 for ownership zero handling; use O’(i) = max(O(i), ε).
    - Enforce Σ log O’(i∈L) ≥ log(min_product) and/or ≤ log(max_product).
    - If the solver cannot accept logs, use a precomputed constant vector of log(O’(i)) as coefficients in linear constraints.
  - Ensure constraints are applied to the same binary decision variables used for player selection.
  - Maintain existing lineup size, salary cap, stacking constraints.
- Sanity check: run a few mixes of flags to verify feasibility and counts.

### 5) Observability and logging updates
- `src/observability.py` calls remain; ensure `snapshot_lineups` captures final lineups only.
- Update log lines in `src/cli.py`:
  - Log total generated lineups and elapsed time.
  - On infeasible runs, log a clear message and exit 0 with 0 lineups written.

### 6) Reporting
- `src/reporting.py`:
  - Ensure workbook rendering does not assume filtered/unfiltered split.
  - Keep sheet/tab naming stable; adjust any references if needed.
- Sanity check: open the generated XLSX and confirm data integrity.

### 7) Tests
- Add/adjust tests under `tests/`:
  - Enforce Σ projection min.
  - Enforce Σ ownership min/max.
  - Enforce Π ownership min/max via log.
  - Combined constraints scenario.
  - Infeasible constraints return 0 lineups and write valid (empty) outputs.
  - Removal of deprecated flag `--min-player-projection` from CLI.
  - Outputs present: only `lineups.json`, `lineups.xlsx` in run dir.

### 8) Cleanup
- Remove `filters.py` if fully unused; otherwise prune dead code and references.
- Update `README.md` and help text:
  - Document constraint flags and outputs.
  - Note removal of deprecated flag and filtered/unfiltered outputs.

### 9) Rollout sanity script
- Add a short example command in `README.md` for quick verification:
  - `python -m src.cli --lineups 200 --min-sum-projection 120 --max-sum-ownership 4.2`

### Acceptance (matches spec)
- Only valid lineups are produced; no post-run filtering.
- Only `lineups.json` and `lineups.xlsx` are written per run.
- Deprecated flag removed; CLI and docs updated.
- Infeasible constraints yield zero lineups with clear logging.
