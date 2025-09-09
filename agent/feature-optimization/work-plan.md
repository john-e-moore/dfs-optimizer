### Work plan: multithreading default and incremental model reuse

This plan is organized for iterative execution with measurable checkpoints [[memory:8449028]].

### Phase 1 — Enable CBC multithreading by default (low effort)
- Tasks:
  - Detect CPU count when `Parameters.solver_threads` is None.
  - Pass detected thread count to `pulp.PULP_CBC_CMD(threads=...)`.
  - Add log line noting effective threads and any time limit.
  - Keep explicit user value authoritative.
- Files:
  - `dfs_optimizer/optimizer.py` (centralize defaulting), or `dfs_optimizer/cli.py` (wire default into `Parameters`). Prefer optimizer for single source of truth.
- Acceptance:
  - Functional parity when `--solver-threads 1`.
  - Speedup observed on multi-core for 500–2000 lineups vs. single-thread baseline.

### Phase 2 — Incremental model reuse in `generate_lineups` (moderate effort)
- Tasks:
  - Build `LpProblem` and decision vars `x[i]` once outside the main loop.
  - Add base constraints once: roster size, position counts, salary bounds, stack, QB vs DST.
  - Conditionally add game-stack variables/constraints only when `params.game_stack > 0`.
  - Inside the loop:
    - Solve using the same `prob` and `x`.
    - Extract selected indices and append a single uniqueness constraint `sum(x[i] for i in selected) <= 8`.
    - Repeat until target or infeasible.
  - Ensure objective is set once and not duplicated; ensure no leakage of per-iteration temporary variables.
- Files:
  - `dfs_optimizer/optimizer.py` (refactor `generate_lineups`).
- Acceptance:
  - With `--solver-threads 1` and no time limit, the first K lineups match legacy behavior.
  - ≥2× speedup for 500–2000 lineups on typical slate with threads set to CPU count.

### Phase 3 — Optional per-iteration time limit (no behavior change by default)
- Tasks:
  - Keep honoring `Parameters.solver_time_limit_s` as per current code.
  - Document recommended values (e.g., 0.25–0.5s) when throughput is prioritized.
  - Add logging to confirm time limit application per iteration.
- Files:
  - `dfs_optimizer/optimizer.py` (logging only).
- Acceptance:
  - When time limit is set, runs complete faster with negligible lineup quality loss on most slates.

### Phase 4 — Rollback switch and documentation
- Tasks:
  - Add environment variable `DFS_OPTIMIZER_DISABLE_INCREMENTAL=1` to force legacy rebuild-per-iteration mode.
  - Document in `README.md` under performance tuning.
- Files:
  - `dfs_optimizer/optimizer.py` (conditional path for legacy loop).
  - `README.md` (docs section).
- Acceptance:
  - When env var is set, code path matches legacy execution and produces identical first K lineups (single-thread, no time limit).

### Benchmarks and verification
- Benchmark harness:
  - Input: one representative slate CSV (realistic size).
  - Configs:
    - Baseline: threads=1, no time limit, legacy loop.
    - Phase 1 only: threads=CPU, no time limit.
    - Phase 1+2: threads=CPU, no time limit.
    - Phase 1+2+3: threads=CPU, timeLimit=0.25s (optional).
  - Targets:
    - 500, 2000, 5000 lineups; record wall time and unique lineup count.
    - Validate roster constraints and uniqueness for a sample of outputs.

### Risks and mitigations
- CBC/pulp state reuse pitfalls → add regression tests that perform 20 incremental solves with and without `game_stack`.
- Growth in uniqueness constraints → unchanged from legacy; monitor memory; consider early stop if infeasible.
- Thread saturation on shared machines → allow `--solver-threads` override; document.

### Deliverables
- Code changes in `optimizer.py` (and small `cli.py`/`README.md` updates as needed).
- Benchmark results summary in `agent/feature-optimization/benchmarks.md`.
- Optional: env var-based fallback implemented and documented.


