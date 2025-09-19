### Feature: SaberSim CSV data source and ID mapping

Goal
- Add a CLI flag `-ss`/`--sabersim` that, when set, loads projections from the most recent CSV file matching `data/NFL_*.csv` (filename begins with `NFL_`) instead of the default CSV at `data/DraftKings NFL DFS Projections -- Main Slate.csv`.
- Map SaberSim columns to the project’s canonical schema and flow:
  - Name: column B (`Name`) → `Name`
  - Projection: column I (`SS Proj`) → `Projection`
  - Ownership: column N (`Adj Own`) → `Ownership` (normalized to 0..1 like CSV loader)
  - Player ID: column A (`DFS ID`) becomes the source of DraftKings IDs for the `DK Lineups` tab.
- When `-ss` is passed, do not read `data/DKEntries.csv` for IDs; instead, use the `DFS ID` values from the loaded SaberSim CSV to populate `DK Lineups`.

Data assumptions and mapping
- Required target columns for the optimizer remain: `Name, Team, Opponent, Position, Salary, Projection, Ownership`.
- The SaberSim CSV is expected to contain columns for at least: `Name`, `Team`, `Opponent` (or `Opp`), `Position` (or `Pos`), `Salary`, `SS Proj`, `Adj Own`, and `DFS ID`.
  - Map these as:
    - `Name` → `Name`
    - `Team` → `Team` (uppercase, trimmed)
    - `Opponent`/`Opp` → `Opponent` (uppercase, trimmed)
    - `Position`/`Pos` → `Position` (uppercase, trimmed)
    - `Salary` → `Salary` (numeric)
    - `SS Proj` → `Projection` (numeric, non-negative)
    - `Adj Own` → `Ownership` (numeric; normalize to fraction 0..1)
    - `DFS ID` → used for DK ID mapping when emitting `DK Lineups`
- Rows missing any of the required target columns after mapping are dropped (same policy as existing CSV loader).

CLI changes
- Update `src/cli.py::build_arg_parser`:
  - Add `-ss`/`--sabersim` (action="store_true"): when present, ignore `--projections` path and instead auto-discover the latest CSV matching `data/NFL_*.csv`.
  - Log which file was chosen. If none found, exit with an actionable error message.
- `src/cli.py::main`:
  - If `args.sabersim` is true:
    - Resolve `csv_path = find_latest_sabersim_csv("data/", prefix="NFL_")`.
    - Load via new SaberSim loader (see below) to get a cleaned DataFrame in the canonical schema.
  - Else: keep current CSV path behavior (`load_and_clean(args.projections)`).

Implementation plan
1) New module: `src/sabersim_loader.py`
   - `find_latest_sabersim_csv(directory: str = "data/", prefix: str = "NFL_") -> str`
     - List files matching wildcard `data/NFL_*.csv` under `directory` (filenames beginning with `NFL_`).
     - Return the most recently modified path. If none, raise a descriptive `FileNotFoundError`.
   - `load_and_clean_sabersim_csv(path: str) -> pd.DataFrame`
     - Read the CSV with `pandas.read_csv`.
     - Normalize columns (strip headers), then project to required schema using the mapping described above.
     - Coerce numeric fields; normalize ownership to 0..1 (reuse `data_loader.normalize_ownership`).
     - Uppercase/trim `Team`, `Opponent`, and `Position` to match CSV cleaner.
     - Drop rows with missing required values and assert non-negativity constraints as in `data_loader.clean_projections`.
     - Return the cleaned DataFrame, preserving an extra column `DFS ID` for downstream ID mapping.

2) Source selection in CLI
   - In `src/cli.py::main`:
     - Branch: if `args.sabersim` → call `load_and_clean_sabersim_csv(csv_path)`; else current `load_and_clean(args.projections)`.
     - The rest of the pipeline remains unchanged (players extraction, optimization, reporting).

3) DK Lineups ID mapping from SaberSim
   - Update `src/dk_upload.py` to support an injected name→ID mapping:
     - Add optional parameter to `format_lineups_for_dk`: `name_to_id_override: dict[str, str] | None = None`.
     - If provided, use it for exact name matches before falling back to the DK entries mapping and DST-by-team fallback.
   - Add helper in the same module:
     - `build_name_to_id_map_from_projections(df: pd.DataFrame, id_col: str = "DFS ID") -> dict[str, str]`
       - Map `Name` → `DFS ID` where both are non-empty strings.
   - Update `src/reporting.py::export_workbook`:
     - If `"DFS ID"` exists in `projections_df.columns`, build `name_to_id = build_name_to_id_map_from_projections(projections_df)` and call:
       - `format_lineups_for_dk(lineups_df, projections_df, dk_entries_df=pd.DataFrame(), name_to_id_override=name_to_id)`
     - Else (baseline path), keep current behavior: load DK entries and call `format_lineups_for_dk(lineups_df, projections_df, dk_entries_df)`.
     - Continue to write `extra_tabs={"DK Lineups": dk_lineups_df}` on success, or omit the tab on error as today.

4) Logging and resilience
   - When `-ss` is used, log the discovered SaberSim file path.
   - If the CSV does not contain required columns (`Name`, `Team`, `Opponent`, `Position`, `Salary`, `SS Proj`, `Adj Own`, `DFS ID`), raise a clear error listing the missing headers.
   - `format_lineups_for_dk` continues to log a single warning summarizing unresolved names.

5) Tests
   - `tests/test_sabersim_loader.py` (new):
     - Create a minimal temp CSV with required columns and a few rows; assert that `load_and_clean_sabersim_csv` returns the canonical schema with normalized ownership and types.
     - Test latest-file selection finds the newest `NFL_*.csv` in a temp `data/` directory.
   - `tests/test_reporting_sabersim.py` (new):
     - With a small SaberSim DataFrame (including `DFS ID`) and a toy `lineups_df`, assert `DK Lineups` cells use IDs from `DFS ID` without reading DKEntries.
   - CLI smoke test:
     - Run `src.cli.main(["-ss", "--outdir", tmpdir])` in a controlled environment with a temp `data/NFL_*.csv` and confirm that `lineups.xlsx` contains the `DK Lineups` sheet and ID formatting matches `Name (ID)`.

6) Backward compatibility and performance
   - Default behavior (no `-ss`) is unchanged.
   - When `-ss` is set, only source selection and ID mapping source change; all downstream structures remain the same.
   - Performance impact is minimal: a single CSV read and linear mapping similar to existing CSV loader.

Acceptance criteria
- Running `python -m src.cli -ss` loads projections from the latest `data/NFL_*.csv` and produces `output/<ts>/lineups.xlsx` with tabs: `Projections`, `Parameters`, `Lineups`, `Players`, and `DK Lineups`.
- In `DK Lineups`, player cells are formatted as "Name (ID)" using IDs from the `DFS ID` column of the SaberSim file. No percentages appear.
- With `-ss` disabled, behavior is unchanged and IDs come from `data/DKEntries.csv` as before.
- If no `NFL_*.csv` exists, the program exits with a descriptive message telling the user to place a SaberSim file into `data/`.

Notes and edge cases
- Name normalization: strip/normalize whitespace and apostrophes when building `Name` → `DFS ID` mapping; match exact names in `Lineups` after stripping trailing parentheses (same as current logic).
- DST handling: If a lineup `DST` cell cannot be matched by exact name via the override map, the existing DST-by-team fallback remains available when DK entries are also provided. With `-ss`, the override should eliminate most misses, but unresolved names are still warned once per export.
- If the SaberSim CSV includes extra columns, they are ignored; only mapped columns are used.


