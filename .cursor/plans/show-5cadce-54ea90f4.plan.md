<!-- 54ea90f4-1094-46ee-8c00-01fa13c7b7b7 e640ce57-f724-4466-981f-dfb3ccc84756 -->
## Solver-level showdown rule implementation

### 1. Scope and rule patterns to support

1. Limit initial solver-level support to the specific DSL pattern you’re using that causes thrashing:

- Unconditional rule (no `when`) with a single `enforce` clause that is an `any_of`.
- The `any_of` consists only of `count` clauses whose selectors are **team-only** (no slot/pos/pos_in/type) and have a `min` value.
- Example: `min_5_from_one_team` with `any_of(count(team=TEAM_A, min=5), count(team=TEAM_B, min=5))`.

2. Keep all other rules (e.g., `no_cpt_qbA_with_dstB`, `qbA_cpt_requires_2_rb_wr_te_A`) enforced via the existing post-solve filter to avoid complex MILP encodings right now.

### 2. Translate matching DSL rules into MILP constraints

3. In `generate_lineups_showdown` (in `src/showdown.py`), after building `team_to_idxs` and the existing `min_players_by_team` constraints, add a translation pass over `rules`:

- For each `ConstraintRule` in `rules.values()`:
 - Skip if `rule.when` is not `None`.
 - Skip if `len(rule.enforce) != 1` or the single clause is not an `AnyOf`.
 - Inspect each `AnyOf` option:
 - Require `isinstance(option, CountCondition)` with `selector.team` set and `selector.slot/pos/pos_in/type` all `None`.
 - Require `option.min` present (ignore `max`).
 - Collect the `(team, min)` pairs for all valid options.

4. For each such rule with at least one valid `(team, min)` option:

- Create binary indicator variables `y_rule_option_j` (one per team option) with CBC via PuLP.
- For each `(team, min)` pair:
 - Let `idxs = team_to_idxs[team]`.
 - Add constraint: `sum(x[i] for i in idxs) >= min * y_rule_option_j`.
- Add a final constraint: `sum(y_rule_option_j) >= 1` to encode the `any_of` OR.

5. Leave `rules` and `_violated_rules` unchanged for now:

- The solver-level constraints ensure any optimal solution it returns already satisfies `min_5_from_one_team`.
- The post-solve filter remains as a safety net, but for the encoded pattern, it should never trigger.

### 3. Guardrails and logging

6. Add minimal logging when a rule is successfully encoded at solver level (e.g., rule name and teams/mins) so you can see in logs that the translation happened.
7. Optionally, keep a small counter of how many times the post-solve filter rejects a lineup and, if it exceeds a threshold (e.g., 50), log a warning suggesting the underlying DSL might need a solver-level encoding.

### 4. Tests

8. Add a focused unit test for the new behavior, e.g. `tests/test_showdown_solver_rules.py`:

- Build a tiny synthetic showdown pool with clear `TEAM_A` / `TEAM_B` labels.
- Define a `min_5_from_one_team` rule in DSL form and pass it to `generate_lineups_showdown`.
- Assert that every produced lineup has at least 5 players from one of the two teams, and that the function terminates with the requested number of lineups (or gracefully with fewer if infeasible).

9. Add/extend tests for the DSL parser so the `any_of` + team-only `count` pattern is parsed consistently with what the solver translator expects.

### 5. Documentation / comments

10. In `showdown.py`, add concise comments around the new encoding explaining:

 - Which DSL patterns are recognized.
 - That other rules still use the post-solve filter.

11. Optionally, add a short note to the README showdown DSL section mentioning that certain team-count rules (like `min_5_from_one_team`) are enforced directly in the solver for performance and feasibility reasons.

### To-dos

- [ ] Identify and document the exact showdown DSL patterns to be pushed into the MILP model (any_of over team-only count conditions with min).
- [ ] In `src/showdown.py`, translate matching any_of team-count rules (e.g., min_5_from_one_team) into solver-level constraints using binary indicators.
- [ ] Retain the existing post-solve rule filter as a safety net while ensuring encoded rules should no longer be violated by solver outputs.
- [ ] Add tests to verify that solver-enforced showdown rules (e.g., min 5 from one team) are honored and that optimization terminates without excessive rejections.
- [ ] Document the solver-level encoding behavior in code comments and briefly in the README showdown DSL section.