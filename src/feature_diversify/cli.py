from __future__ import annotations

import argparse
import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .io_excel import (
    DEFAULT_SHEET_NAME,
    LineupRecord,
    SourceKey,
    parse_source_key,
    read_lineups_from_sources,
)
from .selector import SelectionResult, farthest_first_with_quotas, jaccard_distance
from ..dk_upload import load_dk_entries, format_lineups_for_dk


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Select diversified lineups across multiple Excel sources (Jaccard)")
    p.add_argument("--input", action="append", default=[], help="Input Excel path (for validation/discovery; repeatable)")
    p.add_argument(
        "--pick",
        action="append",
        default=[],
        help="Repeatable SOURCE:COUNT where SOURCE is file.xlsx or file.xlsx:Sheet",
    )
    p.add_argument("--sheet-name", default=DEFAULT_SHEET_NAME, help="Sheet name for sources without explicit sheet (default Lineups)")
    p.add_argument("--projection-col", default="Projection", help="Projection column name (for tie-break)")
    p.add_argument("--players-col", default=None, help="Optional single column containing comma-separated players")
    p.add_argument("--roster-cols", default=None, help="Comma-separated roster cols to use (overrides detection)")
    p.add_argument("--allow-shortfall", action="store_true", help="If set, allow picking fewer than quota when source is short")
    p.add_argument("--random-seed", type=int, default=None, help="Random seed (for deterministic tie-break ordering)")
    p.add_argument("--out", required=True, help="Output Excel path for diversified selection")
    return p.parse_args(argv)


def _parse_pick(pick: str, default_sheet: str) -> Tuple[SourceKey, int]:
    if ":" not in pick:
        raise SystemExit(f"Invalid --pick '{pick}'; expected SOURCE:COUNT")
    # Split from right to capture COUNT even if SOURCE includes ':' for a sheet
    left, count_str = pick.rsplit(":", 1)
    try:
        count = int(count_str)
    except ValueError:
        raise SystemExit(f"Invalid count in --pick '{pick}'")
    skey = parse_source_key(left)
    return SourceKey(path=skey.path, sheet=skey.sheet or default_sheet), count


def _build_exposure(selected: List[LineupRecord]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # Player exposures: token form may contain Name|TEAM; recover these parts when possible
    from collections import Counter

    player_counter = Counter()
    team_counter = Counter()
    total = len(selected)

    for rec in selected:
        for tok in rec.player_tokens:
            player_counter[tok] += 1
            if "|" in tok:
                _, team = tok.split("|", 1)
                team_counter[team] += 1

    players_rows = []
    for tok, cnt in player_counter.most_common():
        name, team = (tok.split("|", 1) + [None])[:2] if "|" in tok else (tok, None)
        players_rows.append({
            "Player": name,
            "Team": team or "",
            "#": cnt,
            "%": round(100.0 * cnt / max(1, total), 1),
        })
    teams_rows = []
    for team, cnt in team_counter.most_common():
        teams_rows.append({
            "Team": team,
            "#": cnt,
            "%": round(100.0 * cnt / max(1, total * 9), 1),
        })

    return pd.DataFrame(players_rows), pd.DataFrame(teams_rows)


def _compute_min_dists(selected: List[LineupRecord]) -> List[float]:
    dists: List[float] = []
    sets = [s.player_tokens for s in selected]
    for i, s in enumerate(sets):
        if len(sets) <= 1:
            dists.append(float("nan"))
        else:
            others = sets[:i] + sets[i + 1 :]
            d = min(jaccard_distance(s, o) for o in others) if others else float("nan")
            dists.append(d)
    return dists


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)

    # Parse roster overrides
    roster_cols = None
    if args.roster_cols:
        roster_cols = [c.strip() for c in args.roster_cols.split(",") if c.strip()]

    # Parse picks and quotas
    quotas: Dict[str, int] = {}
    sources: List[SourceKey] = []
    for pick in args.pick:
        skey, count = _parse_pick(pick, args.sheet_name)
        key_str = skey.key()
        quotas[key_str] = quotas.get(key_str, 0) + int(count)
        sources.append(skey)

    if not quotas:
        raise SystemExit("No --pick provided")

    # Validate inputs if provided
    for p in args.input:
        if not os.path.exists(p):
            print(f"Warning: input path not found: {p}")

    # Load candidates
    records = read_lineups_from_sources(
        sources,
        default_sheet=args.sheet_name,
        roster_cols=roster_cols,
        players_col=args.players_col,
        projection_col=args.projection_col,
    )
    if not records:
        raise SystemExit("No lineups found across specified sources")

    # If any quota exceeds available rows in its source
    from collections import Counter

    counts_by_source = Counter(rec.source_key for rec in records)
    shortfalls = []
    for key, need in quotas.items():
        have = counts_by_source.get(key, 0)
        if have < need:
            if not args.allow_shortfall:
                raise SystemExit(f"Quota {need} for {key} exceeds available {have}; use --allow-shortfall to proceed")
            shortfalls.append((key, need, have))

    # Select diversified set
    result: SelectionResult = farthest_first_with_quotas(records, quotas, seed=args.random_seed)
    selected = result.selected

    # If shortfall allowed, verify we fulfilled all feasible picks
    if args.allow_shortfall:
        # Recount by source
        out_counts = Counter(rec.source_key for rec in selected)
        for key, need, have in shortfalls:
            # We can only pick up to 'have'
            if out_counts.get(key, 0) > have:
                raise SystemExit("Internal error: selected more than available")

    if not selected:
        raise SystemExit("Selection produced no lineups")

    # Build Selected sheet
    rows = []
    min_dists = _compute_min_dists(selected)
    for rank, (rec, mind) in enumerate(zip(selected, min_dists), start=1):
        # Split source key into file and sheet
        if ":" in rec.source_key:
            src_file, src_sheet = rec.source_key.rsplit(":", 1)
        else:
            src_file, src_sheet = rec.source_key, args.sheet_name
        base = {
            "Rank": rank,
            "Source File": src_file,
            "Source Sheet": src_sheet,
            "Projection": rec.projection,
            "MinDistToPortfolio": mind,
        }
        # Preserve original columns when possible
        row_dict = {**base}
        for c, v in rec.original_row.items():
            # Avoid overwriting our own fields
            if c in row_dict:
                row_dict[f"{c}_orig"] = v
            else:
                row_dict[c] = v
        rows.append(row_dict)
    selected_df = pd.DataFrame(rows)

    # Build DK-ready replica of Selected (player cells formatted as "Name (ID)")
    try:
        player_cols_all = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
        player_cols = [c for c in player_cols_all if c in selected_df.columns]
        proj_min = pd.DataFrame({"Name": []})
        if player_cols:
            def _extract_name(value: object) -> str:
                s = str(value) if value is not None else ""
                s = s.strip()
                if s.endswith(")") and "(" in s:
                    try:
                        return s.rsplit(" (", 1)[0]
                    except Exception:
                        return s
                return s
            names_series = pd.Series(dtype=object)
            for c in player_cols:
                names_series = pd.concat(
                    [names_series, selected_df[c].dropna().astype(str).map(_extract_name)],
                    ignore_index=True,
                )
            unique_names = sorted(set(n for n in names_series.tolist() if n))
            proj_min = pd.DataFrame({"Name": unique_names})
        dk_entries_df = load_dk_entries()
        dk_selected_df = format_lineups_for_dk(selected_df, proj_min, dk_entries_df)
    except Exception:
        # On any failure, fall back to writing only Selected without DK tab
        dk_selected_df = None

    # Exposure sheets
    players_df, teams_df = _build_exposure(selected)

    # Build per-source summary (selected vs quota vs available)
    out_counts = Counter(rec.source_key for rec in selected)
    summary_rows = []
    for key in sorted(set(list(quotas.keys()) + list(counts_by_source.keys()) + list(out_counts.keys()))):
        summary_rows.append(
            {
                "Source": key,
                "Quota": quotas.get(key, 0),
                "Available": counts_by_source.get(key, 0),
                "Selected": out_counts.get(key, 0),
            }
        )
    summary_df = pd.DataFrame(summary_rows)

    # Metrics row
    metrics_df = pd.DataFrame(
        [
            {
                "Min Pairwise Jaccard": result.min_pairwise_jaccard,
                "Avg Pairwise Jaccard": result.avg_pairwise_jaccard,
            }
        ]
    )

    # Ensure output dir exists
    out_dir = os.path.dirname(args.out) or "."
    os.makedirs(out_dir, exist_ok=True)

    with pd.ExcelWriter(args.out, engine="xlsxwriter") as writer:
        selected_df.to_excel(writer, "Selected", index=False)
        if dk_selected_df is not None:
            dk_selected_df.to_excel(writer, "DK Lineups", index=False)
        players_df.to_excel(writer, "Exposure", index=False)
        teams_df.to_excel(writer, "Teams", index=False)
        metrics_df.to_excel(writer, "Metrics", index=False)
        summary_df.to_excel(writer, "Summary", index=False)

    print(
        f"Wrote {len(selected)} diversified lineups to {args.out} | MinJ={result.min_pairwise_jaccard:.3f} AvgJ={result.avg_pairwise_jaccard:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


