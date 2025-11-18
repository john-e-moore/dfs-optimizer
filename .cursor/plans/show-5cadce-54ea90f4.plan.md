<!-- 54ea90f4-1094-46ee-8c00-01fa13c7b7b7 a0dc751b-5e8d-4d05-aa7d-ed6f785c12a1 -->
# Implement structured showdown constraints

### 1. Refactor contest YAML run configs (do this first)

1. Update `contests-showdown.yaml` structure:

- Replace each `run_1: bash run.sh ...` with a `runs:` list containing objects of flags instead of shell strings.
- For showdown, include at least: `projections`, `mode`, `lineups`, `max_weighted_ownership`, `min_salary` (and any other flags currently used, e.g. `--ss`, `--showdown`).
- Group these under a new `constraints:` (or `config:`) map per contest size, e.g.:
- `constraints.projections: sabersim`
- `constraints.mode: showdown`
- `constraints.runs: [ { lineups: 200, max_weighted_ownership: 34, min_salary: 46000 } ]`.

2. Update `contests.yaml` similarly:

- Replace each `run_N: bash run.sh ...` with a `runs:` list under `constraints:` that captures all flags: `lineups`, `stack`, `bringback`, `game_stack`, `max_weighted_ownership`, `min_salary`, etc.
- Preserve the existing semantics of each run (including multiple runs per contest size) via separate entries in the `runs` array.

3. Adjust `run.sh` / `src/cli.py` loading logic:

- Change config reading to expect structured `constraints` / `runs` objects rather than `run_N` strings.
- Build the equivalent argument set for the CLI from the YAML fields instead of shell-splitting `run_N`.
- Keep backwards compatibility minimal or remove the old `run_N` path if not needed.

### 2. Design and encode the showdown constraint DSL in YAML

4. Finalize the DSL schema under `constraints`:

- Under each contest size in `contests-showdown.yaml`, add a `rules:` map inside `constraints:` for showdown-specific logic.
- Define rule objects as:
- `when` (optional): a `count` condition with `selector` and `min`/`max`.
- `enforce`: list of clauses, each being `count`, `forbid`, or `any_of`.
- Define `selector` objects supporting: `slot`, `team`, `pos`, `pos_in`, `type`.

5. Add example rules matching your described use cases:

- `no_cpt_qbA_with_dstB` using a `forbid` clause.
- `qbA_cpt_requires_2_rb_wr_te_A` using `when` + `count`.
- `min_4_from_one_team` using `any_of` with two `count` branches.
- Place these under `constraints.rules` for one or more contest sizes as a reference.

### 3. Implement parsing & internal models

6. Create Python models for the DSL:

- Add `Selector`, `CountCondition`, `ForbidCondition`, `AnyOf`, and `ConstraintRule` dataclasses/pydantic models in an appropriate module (e.g. `src/constraints/showdown_dsl.py`).
- Implement YAML parsing helpers that map `constraints.rules` from `contests-showdown.yaml` into these models, with validation and clear error messages for bad configs.

7. Integrate contest config loading:

- Extend the existing contest config loader (where `contests.yaml` is read) to also parse `constraints` and `rules`.
- Ensure the CLI entry (`src/cli.py`) surfaces any configuration errors clearly when a contest is selected.

### 4. Apply constraints in the optimizer

8. Map `Selector` to player indices:

- Implement a helper that, given the slate/game and player pool, resolves each `Selector` to the set of lineup decision variables (e.g. x[i] binaries) based on team, position, slot (CPT/FLEX), and type.
- Reuse existing mapping logic where possible (e.g. how classic stacks or ownership constraints currently map to variables).

9. Translate rules into solver logic or filters:

- For `count` clauses, enforce `sum(x_i in selector) >= min` and/or `<= max` in the MIP model.
- For `forbid` clauses, enforce `sum(left) + sum(right) <= 1` (or a refined version capturing the exact pattern you want).
- For `any_of`, implement a simple disjunction mechanism (e.g. auxiliary binaries or post-solve filtering) starting with a post-filter approach for simplicity.

10. Wire showdown constraints into the lineup generation flow:

- When running in showdown mode, load `constraints.rules` for the chosen contest size and apply them when building the optimization problem or when filtering generated lineups.
- Add tests or at least a debug mode to print which constraints are active and how many lineups they filter out.

### 5. Testing and validation

11. Add unit tests and/or small integration tests:

- Test YAML parsing of `constraints` and `rules` with the example configs.
- Test that specific synthetic player pools + constraints yield or forbid expected lineups (e.g., a lineup with CPT QB A + DST B is rejected).

12. Update documentation:

- Update `README.md` (or a dedicated docs file) to describe the new `constraints` and `rules` structure for both classic and showdown contests.
- Include a few copy-paste-ready YAML examples for common showdown patterns so you can quickly adjust rules per contest size.

### To-dos

- [ ] Refactor `contests.yaml` and `contests-showdown.yaml` to replace `run_N` strings with structured `constraints` and `runs` objects, and update `run.sh`/`cli` to consume them.
- [ ] Define the showdown constraint DSL schema under `constraints.rules` in `contests-showdown.yaml` and encode example rules for common patterns.
- [ ] Implement Python models and YAML parsing for the DSL, integrating them into the contest config loader.
- [ ] Map selectors to variables and enforce DSL rules in the optimization or filtering pipeline for showdown mode.
- [ ] Add tests for config parsing and constraint behavior, and update docs/README with new YAML structure and examples.