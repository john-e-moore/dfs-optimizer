<!-- ec0840b2-2666-4804-8b78-abc8a53f25dc cc73e5ea-405f-4a9c-9946-87c881a627c0 -->
# Implement DraftKings Showdown Mode (--showdown)

### Scope

- Add a `--showdown` CLI flag to switch the pipeline into DraftKings showdown captain-mode.
- Load SaberSim `NFL_*.csv` and label each player-row as `CPT` or `FLEX`; drop zero-projection rows.
- Optimize 6-player lineups with exactly 1 `CPT` and 5 `FLEX`, classic $50k cap, and no position minima.
- Export `lineups.xlsx` with columns `CPT`, `FLEX1..FLEX5`, plus the usual tabs and metadata.
- Update `run.sh` to accept and forward `--showdown`.

### Key Changes

- CLI flag and branching in `src/cli.py`:
  - Parse `--showdown`.
  - If set, require SaberSim input and route to showdown loader/optimizer and showdown dataframe/export.
```30:80:/home/john/dfs-optimizer/src/cli.py
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DFS Lineup Optimizer")
    # ... existing flags ...
    p.add_argument("--ss", "--sabersim", dest="sabersim", action="store_true", ...)
    # add:
    # p.add_argument("--showdown", action="store_true", help="Optimize DraftKings showdown (CPT + 5 FLEX)")
    return p
```

- SaberSim showdown loader in `src/sabersim_loader.py`:
  - New function `load_and_clean_sabersim_csv_showdown(path)`:
    - Reuse existing column normalization.
    - Group by `Name` (and `Team`), label higher-salary as `CPT`, other as `FLEX` in new column `ShowdownRole`.
    - Drop rows where `Projection == 0`.
    - Detect whether CPT `Projection` is already 1.5× FLEX; if not, multiply CPT `Projection` by 1.5 (with tolerance, e.g., 5%).

- Showdown optimizer in new `src/showdown.py`:
  - `ShowdownEntry` dataclass: `name, team, opponent, base_position, role (CPT|FLEX), salary, projection, ownership`.
  - `generate_lineups_showdown(entries, params)` (pulp MILP):
    - Decision var per entry; objective = sum(projection·x).
    - Constraints: sum(x) == 6; sum(CPT) == 1; sum(FLEX) == 5; per-player (by name+team) `x_cpt + x_flex <= 1`; `sum(salary·x) <= 50000` and `>= params.min_salary`.
    - Ownership/projection min/max constraints reused where applicable.
    - Uniqueness: `sum(x_selected) <= 5` between iterations.
  - `lineups_to_dataframe_showdown(lineups, start_time_map)`:
    - Output columns: `Rank, Projection, Salary, Sum Ownership, Product Ownership, Weighted Ownership, CPT, FLEX1..FLEX5`.
    - Order FLEX by (start time, projection) for determinism.

- Reporting updates in `src/reporting.py`:
  - `build_players_exposure_df`:
    - Detect showdown columns (`CPT`, `FLEX1..FLEX5`) and include them in exposure aggregation.
  - DK tab: keep current best-effort mapping; optional later enhancement to handle `CPT/UTIL` explicitly.

- CLI flow (showdown path) in `src/cli.py` main():
  - If `args.showdown`:
    - Resolve latest SaberSim CSV via `find_latest_sabersim_csv()`; load via `load_and_clean_sabersim_csv_showdown()`.
    - Snapshot cleaned projections.
    - Build `ShowdownEntry` list; call `generate_lineups_showdown`.
    - Load single JSON with `slate_loader` as today; build `lineups_to_dataframe_showdown`.
    - Export workbook via `export_workbook` (unchanged signature).

- Shell entrypoint `run.sh`:
  - Add `SHOWDOWN` env var pass-through, and forward `--showdown` when enabled.
  - Example: `bash run.sh --ss --showdown`.

### Notes & Invariants

- Do not add Python files under `agent/`; all implementation lives under `src/`. Scripts stay in repo root (per preferences).
- FLEX positions are indistinguishable; lineup uniqueness is set-based via MILP cuts.
- Validation step auto-detects CPT projection scaling; no manual user toggle needed.

### Acceptance

- `bash run.sh --ss --showdown` creates `output/<ts>/lineups.xlsx` with `CPT, FLEX1..FLEX5` columns and ≥1 lineup.
- Cleaned projections CSV snapshot includes `ShowdownRole` and no zero-projection rows.
- Classic mode remains unaffected.

### To-dos

- [ ] Add --showdown flag and branch control flow in src/cli.py
- [ ] Implement load_and_clean_sabersim_csv_showdown with CPT/FLEX labeling and zero-projection drop
- [ ] Create src/showdown.py with MILP for CPT+5 FLEX and dataframe builder
- [ ] Update build_players_exposure_df to support CPT/FLEX columns
- [ ] Wire showdown loader+optimizer+dataframe into cli main() flow
- [ ] Update run.sh to accept SHOWDOWN and forward --showdown
- [ ] Run a small showdown solve and verify lineups.xlsx output
- [ ] Document showdown usage and example command in README