## Diversified Lineup Selector (Jaccard-only, per-source quotas)

### Goal

Select an exact number of lineups from each provided source (file or sheet) while maximizing portfolio diversification globally using Jaccard distance over player sets. Add an ownership-aware tie-breaker as a follow-up.

This operates on the Excel workbooks produced by `run_bundle_multiple.sh` and related workflows (e.g., `run_bundle.sh`, `tools/aggregate_lineups.py`), where each workbook contains a `Lineups` sheet with roster columns and metadata.

### Inputs

- Sources: one or more Excel workbooks, each possibly with multiple sheets.
  - Multiple files (e.g., under `output/<timestamp>/*.xlsx`), each with a `Lineups` sheet; and
  - A single workbook with multiple sheets of lineups; or a mix of both.
- Per-source quotas: user specifies counts per source key.
  - Source key format: `file.xlsx` (implies default `Lineups` sheet) or `file.xlsx:SheetName` (specific sheet).
  - The final selection must honor the exact counts per source while maximizing diversification across the entire chosen set.
- Column expectations (auto-detected, overridable via CLI flags):
  - Preferred roster columns (as produced by the existing pipeline): `QB`, `RB1`, `RB2`, `WR1`, `WR2`, `WR3`, `TE`, `FLEX`, `DST`.
  - Alternatively, a single `players` column with a comma-separated 9-player list can be supported.
  - Optional numeric columns: `Projection` (used for tie-break), `Ownership` (reserved for v2 tie-break), plus any provenance labels (e.g., `Bundle`, `QB`, `Game`).

### Objective

- Let two lineups have player sets A and B (normalized tokens like `Name|Team|Pos`).
- Jaccard distance: \( d(A, B) = 1 - \frac{|A \cap B|}{|A \cup B|} \).
- Portfolio selection: choose \(K = \sum_i q_i\) lineups, honoring per-source quota \(q_i\), to maximize the minimum pairwise distance among selected lineups (max–min diversification).

### Algorithm

1) Normalize each lineup to a set of player identifiers. Default tokenization: `Player Name (TEAM)` → `Player Name|TEAM|POS` if POS is available; otherwise `Player Name|TEAM`.
2) Precompute pairwise distances or maintain incremental min-distance values on the fly.
3) Farthest-first greedy with group (source) quotas:
   - Seed: lineup with highest average Jaccard distance to the global pool; fallback to highest `Projection` if needed.
   - Iterate: among candidates from sources with remaining quota, pick the lineup that maximizes its minimum distance to the currently selected set.
   - Tie-breakers: higher `Projection`, then deterministic row id. (v2: ownership-aware tie-break.)

Complexity considerations: For N up to ~2,000 and ~9 players/lineup, a dense distance approach is acceptable. If N grows larger, we can optimize using integer bitsets or sparse indexing.

### CLI and Script

- Python (no Python files under `agent/`; place code under `src/`):
  - `src/feature_diversify/io_excel.py` – load files/sheets, infer roster columns, normalize player sets.
  - `src/feature_diversify/selector.py` – Jaccard distance and farthest-first greedy with quotas.
  - `src/feature_diversify/cli.py` – CLI wrapper.
- Root-level shell wrapper:
  - `run_diversify.sh` – convenience wrapper that calls the CLI with pass-through args.

### CLI Usage (examples)

- Multiple files (single `Lineups` sheet in each):

```bash
python -m src.feature_diversify.cli \
  --input output/20251104_101500/flat_small_u1k.xlsx \
  --input output/20251104_101500/flat_small_o1k.xlsx \
  --input output/20251104_101500/flat_mid_1k_3k.xlsx \
  --pick output/20251104_101500/flat_small_u1k.xlsx:5 \
  --pick output/20251104_101500/flat_small_o1k.xlsx:6 \
  --pick output/20251104_101500/flat_mid_1k_3k.xlsx:5 \
  --out output/20251104_101500/diversified.xlsx
```

- Single file with multiple sheets (names coming from upstream labels):

```bash
python -m src.feature_diversify.cli \
  --input output/20251104_101500/bundle.xlsx \
  --pick output/20251104_101500/bundle.xlsx:Small2:5 \
  --pick output/20251104_101500/bundle.xlsx:Small2_BR:6 \
  --pick output/20251104_101500/bundle.xlsx:Small2_BR_GS:5 \
  --out output/20251104_101500/diversified.xlsx
```

Flags:

- `--input PATH` (repeatable). Used to validate existence and speed up discovery; sources are ultimately determined by `--pick` keys.
- `--pick SOURCE:COUNT` (repeatable). SOURCE is `file.xlsx` or `file.xlsx:Sheet`.
- `--sheet-name` (default `Lineups`) if upstream differs.
- Optional overrides: `--projection-col`, `--players-col`, `--roster-cols QB,RB1,RB2,WR1,WR2,WR3,TE,FLEX,DST`, `--random-seed`.

### Output

Writes an Excel workbook (default path given by `--out`):

- Sheet `Selected`: one row per selected lineup with:
  - `Source File`, `Source Sheet`, `Rank` (within selected), `Projection`, `MinDistToPortfolio` (min pairwise Jaccard vs. selected set).
  - Original roster columns (`QB`, `RB1`, `RB2`, `WR1`, `WR2`, `WR3`, `TE`, `FLEX`, `DST`) and any present metadata columns preserved from the source row.
- Sheet `Exposure`:
  - Player exposures: `Player`, `Team`, `Position` (if recoverable), `#`, `%`.
  - Team exposures (if team tokens available): `Team`, `#`, `%`.
  - Selection metrics: `Min Pairwise Jaccard`, `Avg Pairwise Jaccard`, and per-source quota attainment.
- Logs print a summary: achieved minimum distance, number of candidates per source, any shortfalls.

### Edge Cases & Validation

- Quota > available rows: fail with a clear error, or allow `--allow-shortfall` to pick as many as possible from that source.
- Duplicates across sources: deduplicate by normalized player set unless `--allow-duplicates` is set.
- Roster columns mismatch: auto-detect commonly used columns; allow explicit overrides. If neither roster columns nor a `players` column is found, the source is skipped with a warning.
- Missing `Projection`: allowed, but tie-break falls back to row order; a warning is logged.

### Next Step (not in v1)

Ownership-aware tie-breaker:

- On ties (or near-ties) by Jaccard min-distance, prefer candidates with lower shared-ownership penalty: minimize \( \sum_{p \in A \cap S} \text{Ownership}(p) \) where \(S\) is the union of players already selected.
- CLI additions: `--ownership-col`, `--tie-break ownership`.

### Deliverables

- Spec document (this file): `agent/feature-diversify/spec.md`.
- Python modules:
  - `src/feature_diversify/io_excel.py`
  - `src/feature_diversify/selector.py`
  - `src/feature_diversify/cli.py`
- Root wrapper script: `run_diversify.sh`.
- Unit tests and small fixtures under `tests/feature_diversify/`.

### Acceptance Criteria

- CLI can read multiple Excel sources and enforce per-source quotas while maximizing min pairwise Jaccard across the full selection.
- Output workbook includes `Selected` and `Exposure` sheets with metrics and provenance.
- Handles both roster-column and `players`-column formats without code changes (overrides available).
- Clear error on quota shortfall unless `--allow-shortfall` is provided.


