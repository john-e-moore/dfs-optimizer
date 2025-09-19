### Feature: Add “DK Lineups” tab to all final Excel outputs

Goal
- Add a new tab named `DK Lineups` that mirrors the `Lineups` tab but formats each player cell as "Name (ID)" where ID is the DraftKings Player ID from `data/DKEntries.csv`.
- Apply this to all final workbooks:
  - Single run output: `output/<timestamp>/lineups.xlsx`
  - Aggregated QB stacks output: `.../qb_stacks.xlsx`
  - Aggregated Game stacks output: `.../game_stacks.xlsx`
- If any player ID cannot be resolved, log a clear warning listing the missing names.

Data sources and mapping
- Source of names to map: the lineup player columns in the `Lineups` sheet: `QB, RB1, RB2, WR1, WR2, WR3, TE, FLEX, DST`.
- Player base name extraction: strip any trailing parenthetical in the existing lineup values. Examples:
  - "Justin Herbert (25.3%)" -> base name "Justin Herbert"
  - "A (X)" -> base name "A"
- DK IDs: read from `data/DKEntries.csv`.
  - Starting around row 8 there is a player table with headers including `Position, Name + ID, Name, ID, Roster Position, Salary, Game Info, TeamAbbrev, AvgPointsPerGame`.
  - Build a mapping primarily from `Name` -> `ID` for all rows where `ID` is present.
  - Also retain `Position` and `TeamAbbrev` for fallback logic.
- Matching rules (in order):
  1) Exact match by `Name` from projections/lineups base name to `Name` in DKEntries.
  2) If not found and the lineup column is `DST`, perform a DST fallback:
     - Resolve the projected player row by name from `projections_df` to confirm `Position == 'DST'` and capture `Team`.
     - Find DKEntries row with `Position == 'DST'` and `TeamAbbrev` equal to that `Team` (case-insensitive). Use its `Name` and `ID`.
  3) If still not found, record the base name in a missing set and leave the cell as the base name (no ownership %, no ID) in the DK sheet.
- Formatting for `DK Lineups` cells: always "{ResolvedName} ({ID})" for matched players. No ownership percentages should appear anywhere in this tab.

Implementation plan
1) New module: `src/dk_upload.py`
   - `load_dk_entries(csv_path: str = "data/DKEntries.csv") -> pd.DataFrame`
     - Read the CSV; locate the section with headers containing at least `Name` and `ID`.
     - Return a DataFrame with columns normalized to: `Name` (str), `ID` (str), `Position` (str), `TeamAbbrev` (str).
   - `build_name_to_id_map(df: pd.DataFrame) -> dict[str, str]`
     - Map exact `Name` -> `ID` where `ID` is not null/empty.
   - `format_lineups_for_dk(lineups_df: pd.DataFrame, projections_df: pd.DataFrame, dk_entries_df: pd.DataFrame, logger) -> pd.DataFrame`
     - Identify player columns present among: `QB, RB1, RB2, WR1, WR2, WR3, TE, FLEX, DST`.
     - For each cell in those columns, extract base name (strip trailing ` ( ... )`).
     - Try exact `Name` -> `ID` via the name map.
     - For `DST` column (or when projections shows that `Name` is a DST), fallback by matching `Team` from `projections_df` to `TeamAbbrev` in DK entries where `Position == 'DST'`.
     - Collect any unresolved names into `missing_names: set[str]`.
     - Return a new DataFrame copy of `lineups_df` with only the player columns replaced by "Name (ID)" where resolved; unresolved remain as base name (no ownership %, no ID).
     - After transformation, if `missing_names` is non-empty, log one warning line like: `Missing DK IDs for N players: <sorted list>`.

2) Extend Excel writing to support extra tabs
   - Update `src/io_utils.py::write_excel_with_tabs` signature to accept `extra_tabs: dict[str, pd.DataFrame] | None = None`.
     - Write existing tabs: `Projections`, `Parameters`, `Lineups`, optional `Players`.
     - If `extra_tabs` is provided, iterate in insertion order and write each sheet with `df.to_excel(writer, sheet_name=<name>, index=False)`.
     - Update the info log string to include `, DK Lineups` when present.

3) Add DK Lineups to single-run workbook
   - Update `src/reporting.py::export_workbook`:
     - Load DK entries via `load_dk_entries()` once per export.
     - Build `dk_lineups_df = format_lineups_for_dk(lineups_df, projections_df, dk_entries_df, logger)`.
     - Call `write_excel_with_tabs(..., players_df=players_df, extra_tabs={"DK Lineups": dk_lineups_df})`.

4) Add DK Lineups to aggregated workbooks
   - Update `tools/aggregate_lineups.py`:
     - Add optional CLI arg `--dk-entries` (default `data/DKEntries.csv`).
     - After computing `combined` and before writing, create `dk_lineups_df` by applying the same transformation used above to `combined`:
       - Use the same player column detection and base-name stripping.
       - For fallback that needs `Team`/`Position`, attempt to resolve using only `combined` when possible (e.g., `DST` column known). If not available, perform name-only match first; DST fallback can be based on the base name heuristics where team equals the base name for DST rows when exact name is missing. Keep logging of unresolved names.
     - Write both sheets in the same output workbook: original aggregated `sheet_name` (default `Lineups`) and `DK Lineups`. Keep the existing `Summary` sheet logic unchanged.

5) Logging
   - Use the existing project logger for warnings.
   - Single-run path: log at most one line summarizing all unresolved names per export.
   - Aggregation path: similarly, one summary line; include the output path in the message for traceability.

6) Tests
   - `tests/test_reporting.py`
     - Add a test that invokes `write_excel_with_tabs` through `export_workbook` and asserts the resulting workbook has a `DK Lineups` sheet.
     - Verify that all player cells in `DK Lineups` player columns end with `)`, contain digits inside parentheses, and do not contain `%`.
   - `tests/test_cli.py` or new test:
     - After a minimal CLI run, open the produced `lineups.xlsx` and assert `DK Lineups` tab exists.
   - `tests/test_tools_aggregate_lineups.py` (new):
     - Create two tiny source xlsx files with `Lineups` sheets; aggregate to an out workbook; assert `DK Lineups` is present and formatted.
   - Unit tests for `src/dk_upload.py`:
     - Parsing `DKEntries.csv` slice into a normalized DataFrame.
     - Name-to-ID mapping and DST fallback behavior.

7) Backward compatibility and performance
   - Default paths remain unchanged; new code uses `data/DKEntries.csv` by default.
   - If `DKEntries.csv` is missing or unreadable, still write the `DK Lineups` sheet but it will be identical to base names and a warning will be logged.
   - The formatting pass is linear in number of lineup rows and cheap compared to optimization; acceptable to execute on each export and aggregation.

Acceptance criteria
- Running `./run.sh` produces `output/<ts>/lineups.xlsx` with tabs: `Projections`, `Parameters`, `Lineups`, `Players`, and `DK Lineups`.
- Running `./run_qb_stacks.sh` produces a `qb_stacks.xlsx` with at least `Lineups`, `Summary`, and `DK Lineups`.
- Running `./run_game_stacks.sh` produces a `game_stacks.xlsx` with at least `Lineups`, `Summary`, and `DK Lineups`.
- In every `DK Lineups` tab:
  - Player columns contain values like "Justin Herbert (40058159)"; no percentages.
  - For any unresolved player, their cell shows only the base name (no parentheses), and a warning is logged listing them.

Notes and edge cases
- Name collisions: if multiple DK rows share the same `Name`, take the first occurrence (consistent with current `build_players_exposure_df` name handling). This mirrors the common case in DK data where names are unique within a draft group.
- Whitespace/quotes: strip extraneous whitespace and normalize apostrophes when comparing names.
- Team codes are compared case-insensitively and trimmed; handle minor variations in DK CSV (e.g., trailing spaces in `Name`).
