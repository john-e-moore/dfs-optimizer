# Implement Contest Classification Script

### Scope
Build `scripts/get_contests.py` to:
- Download daily `contests.json` and the slate JSON `{dg}.json` from S3
- Read `data/DKEntries.csv` (columns A–N) and enrich with entrants and field-size classification from `src/contests.yaml`
- Write `data/DKEntriesClassified.csv`

### Files
- Create `scripts/get_contests.py`
- Verify dependencies; add to `requirements.txt` only if missing: `boto3`, `pandas`, `pyyaml`

### Implementation Steps
1) CLI and environment
- Parse `date` positional arg (`YYYY-MM-DD`) via `argparse`; validate with `datetime.strptime`
- Read env vars: `DK_CONTESTS_S3_BUCKET`, `DK_CONTESTS_S3_PREFIX`, `DK_CONTESTS_AWS_REGION` (default `us-east-2`)
- If bucket or prefix empty, exit with clear error

2) Download contests.json
- S3 URI: `s3://{bucket}/{prefix}/{date}/nfl/contests.json`
- Create `data/` if needed; save to `data/contests.json`

3) Load DK entries
- Read `data/DKEntries.csv` with `pandas.read_csv(usecols=range(14))`
- Ensure `Contest ID` column present; coerce IDs to string (strip/normalize)

4) Map contests and merge
- Load `data/contests.json` (list of objects)
- Build frame with columns: `id` (as string), `m` (entrants), `dg` (slate id)
- Left-merge onto entries on `Contest ID` == `id`
- Add `num_entrants` from `m`

5) Validate slate and fetch slate JSON
- Compute unique `dg` from merged rows with matches; if not exactly one, raise with summary of counts
- S3 URI: `s3://{bucket}/{prefix}/{date}/nfl/{dg}.json`; save to `data/{dg}.json`

6) Classification from YAML
- Load `src/contests.yaml`
- For each row, assign `field_size_classification` using the range with `min_entrants <= num_entrants <= max_entrants`
- If no range matches, set empty and warn

7) Output
- Write `data/DKEntriesClassified.csv` (same order as input columns, plus `num_entrants`, `field_size_classification`)
- Print summary: slate id, matched rows count, classification counts

### Sanity-Check Run (after implementation)
- Example:
  - `DK_CONTESTS_S3_BUCKET=... DK_CONTESTS_S3_PREFIX=... DK_CONTESTS_AWS_REGION=us-east-2 python scripts/get_contests.py 2025-11-10`
- Verify files written: `data/contests.json`, `data/{dg}.json`, `data/DKEntriesClassified.csv`
- Confirm single slate id and expected classification distribution

### Notes
- No changes to `src/contests.yaml` expected
- Script logs warnings for missing `Contest ID` matches; rows remain with blank enrichment
- Network/404 errors from S3 are surfaced with clear messages