## Constraints v2 – Replace Filters With Hard Constraints

### Objective
- **Goal**: Replace the listed filters with optimizer constraints so that no generated lineup violates them.
- **Outcome**: All logic formerly implemented as post-generation filtering is enforced during optimization.

### Scope
- Convert the following CLI flags from post-run filters into optimization-time constraints:
  - `--min-sum-projection` (float): Minimum total projection per lineup.
  - `--min-sum-ownership` (float 0..1): Minimum sum of player ownership fractions per lineup.
  - `--max-sum-ownership` (float 0..1): Maximum sum of player ownership fractions per lineup.
  - `--min-product-ownership` (float 0..1): Minimum product of player ownership fractions per lineup.
  - `--max-product-ownership` (float 0..1): Maximum product of player ownership fractions per lineup.
- Deprecate and remove `--min-player-projection` (replaced by `--min-sum-projection`).
- Remove any post-generation filtering logic and dual “filtered/unfiltered” outputs.

### Constraint Definitions
- Let `L` be a lineup, `P(i)` the projection for player `i`, and `O(i) ∈ [0,1]` the ownership fraction.
- Projection Sum: if provided, enforce Σ P(i ∈ L) ≥ `--min-sum-projection`.
- Ownership Sum:
  - if `--min-sum-ownership` provided: Σ O(i ∈ L) ≥ value
  - if `--max-sum-ownership` provided: Σ O(i ∈ L) ≤ value
- Ownership Product:
  - if `--min-product-ownership` provided: Π O(i ∈ L) ≥ value
  - if `--max-product-ownership` provided: Π O(i ∈ L) ≤ value
  - Note: if the solver requires linearization, apply log transform: Σ log O(i ∈ L) ≥ log(value) or ≤ log(value), skipping players with O(i)=0 or handling via small epsilon.

### Data Requirements
- Projections and ownership fractions must be available per player prior to optimization.
- Ownership is represented as a fraction in [0,1].

### CLI & UX
- Keep existing flags and help text semantics, but enforce as constraints.
- Remove `--min-player-projection` from CLI and docs; reference replacement in help/changelog.

### Outputs
- Write a single set of outputs per run:
  - `lineups.json`
  - `lineups.xlsx`
- Do not produce separate “filtered” or “unfiltered” variants.

### Behavior & Edge Cases
- Constraints are enforced in the optimization model; no post-processing filters.
- If constraint set is infeasible, return zero lineups and log a concise infeasibility message.
- Validate inputs: ownership and product thresholds must be within [0,1]; projection thresholds must be ≥ 0.
- If both min and max variants of the same metric are provided, validate min ≤ max.

### Acceptance Criteria
- Any lineup produced satisfies all provided constraints.
- No code path performs post-run filtering.
- Only `lineups.json` and `lineups.xlsx` are written.
- Deprecated flag `--min-player-projection` is removed and documented as replaced by `--min-sum-projection`.
