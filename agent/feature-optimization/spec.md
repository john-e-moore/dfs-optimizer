### Title
Low-effort speedups: CBC multithreading defaults and incremental MILP reuse

### Objectives
- Reduce wall time to generate 1k–10k lineups with zero or near-zero accuracy loss.
- Achieve better-than-current scaling by avoiding per-iteration rebuilds.
- Maintain existing CLI/API; defaults should “just work” faster on common hardware.

### In scope
- Enable multi-threading by default for CBC when `Parameters.solver_threads` is not provided.
- Refactor `optimizer.generate_lineups` to reuse a single MILP model across iterations, adding only uniqueness constraints between solves.
- Keep `solver_time_limit_s` semantics; optionally recommend values, but default remains None (no change in behavior).

### Out of scope
- Switching solvers (e.g., to OR-Tools CP-SAT).
- Heuristic diversification, projection jitter, or aggressive pre-pruning.
- Changing lineup rules/constraints or output formatting.

### Current behavior (summary)
- For each lineup, a fresh CBC model is built (variables, constraints) and solved.
- Uniqueness is enforced by adding a new constraint for each previous lineup: `sum(x_i in previous) <= 8`.
- This incurs repeated model construction and presolve cost that scales superlinearly with lineup count.

### Proposed design

1) CBC multithreading default
- If `Parameters.solver_threads` is None, detect `os.cpu_count()` and pass that to `pulp.PULP_CBC_CMD(threads=...)`.
- Respect explicit user input; only apply a default when unset.
- Continue to pass `timeLimit` from `Parameters.solver_time_limit_s` when provided.

2) Incremental model reuse in `generate_lineups`
- Build once:
  - Create `LpProblem` and the binary decision variables `x[i]` for all players.
  - Add position count constraints, roster size, salary bounds.
  - Add stack constraints, QB vs DST restriction.
  - Add game stack constraints and any auxiliary vars only when `params.game_stack > 0`.
- Iterate N times (until target lineups or solver reports infeasible/optimality issues):
  - Solve the same model instance via CBC.
  - Extract selected indices from `x`.
  - Append a single uniqueness constraint using the selected indices: `sum(x[i] for i in selected) <= 8`.
  - Repeat solve without recreating variables/constraints.
- Notes:
  - Pulp/CBC supports repeated `solve` calls on the same `LpProblem` while adding constraints between solves.
  - No constraints are removed; model grows linearly with lineup count (as today), but avoids full rebuild and presolve each iteration.
  - When `params.game_stack == 0`, do not create `z_game` binaries at all.

3) Optional per-iteration time limit (no default change)
- Continue to use `Parameters.solver_time_limit_s` (already plumbed) to cap solve time per iteration.
- Recommendation (doc-only, not enforced by default): 0.25–0.5s works well on typical slates with threads enabled if throughput is more important than perfect optimality on each iteration.

### API and CLI changes
- No breaking changes.
- Behavior change: If user does not set `--solver-threads`, we will set threads to `os.cpu_count()` under the hood. Users can force single-threaded by passing `--solver-threads 1`.
- `--solver-time-limit-s` keeps the same semantics; default remains None.

### Implementation details
- File: `dfs_optimizer/optimizer.py`
  - Lift variable and base-constraint construction out of the while loop.
  - Maintain references to `prob` (LpProblem), `x` (dict of player Bool vars), and (optionally) `z_game` when game stack is active.
  - After each solution, construct and add one `LpConstraint` for uniqueness using the selected indices.
  - Reuse the same `PULP_CBC_CMD` instance or rebuild its kwargs each solve with `threads` and `timeLimit`.
- File: `dfs_optimizer/cli.py` (optional convenience)
  - If `args.solver_threads` is None: compute `threads = max(1, os.cpu_count() or 1)` and pass through to `Parameters`.
  - Alternatively, keep CLI unchanged and compute the default inside `optimizer.generate_lineups` to centralize solver policy.

### Acceptance criteria
- Functional parity: With `--solver-threads 1` and no time limit, the first K lineups match the current implementation for the same input and parameters.
- Performance: For generating 500–2000 lineups on a typical slate, wall time improves by ≥2× on a multi-core CPU (with threads set to CPU count) compared to current code.
- Stability: No changes to output schema, CSV/XLSX exports, or logging semantics.

### Risks and mitigations
- Increased memory usage from accumulating uniqueness constraints: unchanged relative to current approach; reuse does not worsen it.
- CBC thread contention: expose the threads parameter; document how to cap threads for shared environments.
- Subtle pulp state reuse issues: add integration tests that perform multiple solves in a single process across different parameter settings (with and without `game_stack`).

### Test plan
- Unit tests: small synthetic player pools to assert lineup validity and uniqueness across 10–20 iterations using the reused model.
- Golden tests: fix a seed and input CSV; assert that lineups 1–20 are identical before/after when single-threaded and no time limit.
- Performance harness: measure wall time for 1k and 5k lineups on a representative slate, comparing current vs. optimized branch with threads=CPU.

### Rollout plan
- Implement behind the scenes; no flags added.
- Bench locally, then confirm on a real slate CSV.
- If regressions occur, keep a fallback path guarded by an env var `DFS_OPTIMIZER_DISABLE_INCREMENTAL=1` to force legacy rebuild-per-iteration behavior for quick rollback.


