<!-- f7b3b26a-d6c0-45ed-b060-b2e798cb544a 001fdf42-4778-47d6-b6f9-a93653481bcd -->
# Fix showdown DK output formatting and CSV layout

### Goals

- Ensure the `DK Lineups` sheet (both bundle and diversify workbooks) formats players as `Name (PLAYER_ID)` in showdown, never `Name (XX%)`.
- Make the pipeline output `DKEntries.csv` with showdown roster headers (`CPT, FLEX, FLEX, FLEX, FLEX, FLEX`) when running with `--showdown`.

### Changes

- Update `src/dk_upload.py`
- Improve name/ID formatting: if a player cell contains parentheses that are not a pure numeric ID (e.g., ends with `%` or letters), strip that and replace with the DK player ID from `DKEntries.csv` mapping.
- Auto-detect showdown vs classic from columns in the provided DataFrame: showdown if `CPT` present; else classic.
- For showdown, return a DataFrame with `CPT, FLEX1..FLEX5` columns (or equivalent) filled with `Name (PLAYER_ID)` strings.

- Update `tools/aggregate_lineups.py`
- Rely on enhanced `format_lineups_for_dk` (no interface change). Ensure showdown columns flow through to the `DK Lineups` sheet.

- Update `src/feature_diversify/cli.py`
- Same: rely on enhanced `format_lineups_for_dk` so diversified workbook’s `DK Lineups` tab uses showdown columns with IDs.

- Update `scripts/run_full_pipeline.py`
- In `build_upload_csv(...)`, branch on presence of `CPT` in `df_dk`:
  - Showdown: map rows to `CPT`, `FLEX1..FLEX5` (or five FLEX columns if already repeated), and write CSV header exactly as DraftKings expects: `CPT, FLEX, FLEX, FLEX, FLEX, FLEX` after the first four DK columns.
  - Classic: retain existing behavior.

### Validation

- With `--showdown`, verify `output/<ts>/diversified.xlsx` has `DK Lineups` with `CPT, FLEX1..FLEX5` and all players as `Name (ID)`.
- Verify `output/<ts>/DKEntries.csv` contains showdown columns and non-empty lineups.
- Classic path unchanged.

### To-dos

- [ ] Enhance src/dk_upload.py to force Name (PLAYER_ID) and detect showdown
- [ ] Ensure aggregator DK Lineups uses showdown columns via dk_upload
- [ ] Ensure diversify DK Lineups uses showdown columns via dk_upload
- [ ] Branch build_upload_csv to write CPT + 5 FLEX output
- [ ] Run a showdown smoke to validate DK Lineups IDs and DKEntries.csv columns