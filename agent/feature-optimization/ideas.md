### Goals
- **Throughput**: 1k–10k lineups in seconds to a few minutes.
- **Scalability**: Sublinear or near-linear scaling with lineup count.
- **Determinism/quality**: Preserve lineup validity and constraints; optionally trade projection optimality for speed when desired.

### Observed structure and likely hotspots
- **MILP per lineup**: `generate_lineups` builds and solves a fresh CBC MILP, then adds a uniqueness cut and repeats. Complexity grows with both players and number of prior solutions due to added constraints and re-solve.
- **Game-stack binary variables**: `z_game` adds |games| binaries per solve.
- **Reconstruction overhead**: Creating the model repeatedly incurs overhead even if 95% of the structure is identical across iterations.

### Optimization ideas (prioritized)

1) Reuse a single solver model and iterate with lazy constraints
- Build the base model once (variables, roster/position/salary/stack constraints).
- After each solve, add a single no-good cut (e.g., sum(x_i for chosen i) <= 8) and re-optimize without rebuilding.
- Prefer a solver that supports lazy constraints and internal callbacks for efficient no-good cut handling.
- **Tradeoffs**: Requires refactor around solver lifecycle; best with OR-Tools CP-SAT or commercial solvers. CBC can do incremental re-solve but lacks true lazy cuts; still gains from not reallocating variables/constraints each loop.

2) Switch solver to OR-Tools CP-SAT
- CP-SAT is extremely fast on 0/1 problems and supports multiple solutions via solution pool or objective-guided search with diversity/no-good cuts.
- Supports multi-threading well; can yield thousands of diverse optimal/near-optimal solutions quickly.
- **Tradeoffs**: Adds dependency; rewrite model with cp-sat (BoolVar, Add, AddEquality, AddAtMost, etc.). Objective is linear and fits CP-SAT. Need to replicate uniqueness and game-stack constraints.

3) Use solution pool/diversification instead of strict optimality for all lineups
- Ask the solver for top-k or near-optimal solutions within a relative optimality gap (e.g., 0.1–1%) and diversity constraints.
- Set a small time limit and request many solutions; often yields more unique, high-quality lineups faster than repeated exact solves.
- **Tradeoffs**: Some lineups may be slightly suboptimal in projection, but typically acceptable; great throughput improvement.

4) Parallelize lineup generation
- Split into N parallel workers, each with disjoint no-good-cut sets or different random seeds and slight perturbations to projections (noise or ties broken differently) to avoid collisions.
- Aggregate and deduplicate at the end.
- **Tradeoffs**: Requires process-level parallelism (GIL-bound in Python), careful seed management, and memory for solver instances.

5) Precompute/strengthen constraints and tighten domains
- Filter player pool aggressively up front: drop dominated players (lower projection and higher salary than another at same position), cap pool sizes per position, remove very low-projection players if they never appear in optimal/near-optimal lineups.
- Add strong valid inequalities (e.g., minimum and maximum counts for RB/WR/TE given salary bounds) to reduce search space.
- Pre-calc team/game indices once (already done) but move to model-global constants; avoid recomputing z_game domains if game_stack==0.
- **Tradeoffs**: Risk of over-pruning and losing exotic lineups; make thresholds configurable.

6) Replace uniqueness cut with per-position Hamming bounds
- Instead of `sum(x_i in chosen) <= 8`, add multiple smaller cuts by position groups to reduce solver degeneracy (e.g., enforce at least 2 changes across RB/WR/TE/FLEX). This may guide search to new regions faster.
- **Tradeoffs**: Slightly more code and constraints; may exclude some feasible but similar lineups; improves diversity.

7) Warm-starts and heuristic starts
- Feed the previous solution as a warm start, then perturb objective weights (tiny noise) or flip a few assignments to produce a new starting incumbent; helps solvers explore quickly.
- **Tradeoffs**: Requires solver API support; with CP-SAT, search is robust without warm starts but they can still help.

8) Column generation / iterative candidate pool
- Start with a reduced player set (top-N by projection/points-per-salary per position). Solve; collect reduced costs/usage stats; add promising players iteratively.
- **Tradeoffs**: Implementation complexity; big payoffs on large slates; risks missing niche stacks unless expansion heuristic is sound.

9) Caching and vectorization around Python loops
- Current loops are moderate, but you can: precompute numpy arrays for projection, salary, ownership; build constraints from arrays; avoid Python-side per-iteration rebuilding by reusing structures.
- **Tradeoffs**: Moderate code refactor; improves constant factors.

10) Game-stack modeling without binaries when possible
- If `params.game_stack == 0`, skip creation of `z_game` entirely (already mostly done) and when >0, consider using Big-M with a single auxiliary variable for the maximum-over-games or enforce game counts via piecewise linear constraints with fewer binaries.
- **Tradeoffs**: Slight modeling complexity; reduces variable count and solve time.

11) Early stopping via objective floors
- Track the best objective so far; if after a time limit the solver cannot beat a floor + epsilon for a new lineup given uniqueness cuts, stop early.
- **Tradeoffs**: Might reduce count in tight slates; predictable runtime.

12) Post-opt diversification without re-solve
- From a solved lineup, do quick local swaps using greedy heuristics under constraints (maintaining salary/positions/stacks) to produce multiple valid variants cheaply.
- Validate with fast checks; only invoke MILP when stuck.
- **Tradeoffs**: Heuristic may miss globally optimal swaps; large throughput gain.

13) Hybrid: MILP seed + CP local search
- Use one optimal solution as seed, then run a constrained neighborhood search (swap 1–2 players respecting constraints) guided by projection gain and diversity.
- **Tradeoffs**: Additional algorithm; predictable speedup.

14) Deterministic randomness for diversity
- Add tiny jitter to projections per worker/iteration (e.g., ±0.25%) so argmax changes, generating diverse but near-optimal lineups without extra constraints.
- **Tradeoffs**: Slight non-determinism unless seeded; tiny projection distortion.

15) Profile and tune CBC
- Expose `solver_threads` (already available) and set to physical cores.
- Set `timeLimit` per iteration (e.g., 0.15–0.5s) to prevent long tail solves; accept best-found incumbent.
- Use solver parameters like `ratioGap` (MIP gap) if available to stop early.
- **Tradeoffs**: Slightly suboptimal lineups; big wins in wall time.

16) Batch export and lazy DataFrame building
- Build `lineups_to_dataframe` once at the end (already done), but ensure no heavy per-lineup pandas operations occur inside the loop. Keep `LineupResult` cheap; defer formatting to export.
- **Tradeoffs**: Small constant-factor win.

### Concrete first steps (low-risk, high ROI)
- Reuse a single model object across iterations; rebuild only the uniqueness cut and re-solve.
- Add per-iteration time limit (e.g., 250ms) and a small relative gap.
- Enable multi-threading and set threads to CPU count.
- Introduce projection jitter per iteration to reduce solver work and improve diversity; keep it configurable.
- Optional: parallelize by running 2–8 worker processes with different seeds; merge and dedupe.

### Scaling expectations
- With CP-SAT and parallel workers, 1k–10k lineups in under a minute is plausible on modern CPUs for typical slate sizes. With CBC plus above improvements, expect 2–5× speedup and better scaling; with time limits and near-optimal acceptance, 10–20× is feasible.
