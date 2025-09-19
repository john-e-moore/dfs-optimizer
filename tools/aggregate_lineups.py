from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import List, Tuple, Optional
import os as _os
import sys as _sys

import pandas as pd
# Ensure project root is on sys.path so 'src' can be imported when running this script directly
try:
    _ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
    if _ROOT not in _sys.path:
        _sys.path.insert(0, _ROOT)
except Exception:
    pass
from src.dk_upload import load_dk_entries, format_lineups_for_dk


@dataclass(frozen=True)
class Source:
    path: str
    value: str


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aggregate Lineups sheets across multiple Excel workbooks")
    p.add_argument("--out", required=True, help="Output Excel path for aggregated results")
    p.add_argument("--column-name", required=True, help="Name of the extra column to add (e.g., QB or Game)")
    p.add_argument(
        "--src",
        action="append",
        default=[],
        help="Repeatable 'PATH::VALUE' pair. VALUE will be written in the new column for all rows from PATH",
    )
    p.add_argument("--sheet", default="Lineups", help="Sheet name to aggregate (default: Lineups)")
    p.add_argument("--engine", default="xlsxwriter", help="ExcelWriter engine (xlsxwriter or openpyxl)")
    p.add_argument("--no-extra-column", action="store_true", help="Do not add an extra column; just concatenate and re-rank")
    p.add_argument("--dk-entries", default="data/DKEntries.csv", help="Path to DK entries CSV for DK Lineups tab")
    return p.parse_args(argv)


def _parse_sources(src_args: List[str]) -> List[Source]:
    sources: List[Source] = []
    for entry in src_args:
        if "::" not in entry:
            raise SystemExit(f"Invalid --src '{entry}'. Expected 'PATH::VALUE'")
        path, value = entry.split("::", 1)
        path = path.strip()
        value = value.strip()
        if not path or not value:
            raise SystemExit(f"Invalid --src '{entry}'. PATH and VALUE must be non-empty")
        sources.append(Source(path=path, value=value))
    if not sources:
        raise SystemExit("No --src provided")
    return sources


def _read_lineups(path: str, sheet_name: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        print(f"Warning: file not found: {path}", file=sys.stderr)
        return None
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except Exception as e:
        print(f"Warning: failed reading '{sheet_name}' from {path}: {e}", file=sys.stderr)
        return None
    if "Projection" not in df.columns:
        print(f"Warning: sheet '{sheet_name}' in {path} missing 'Projection' column; skipping", file=sys.stderr)
        return None
    return df


def _insert_after(df: pd.DataFrame, new_col: str, series: pd.Series, after_col: str) -> pd.DataFrame:
    cols = list(df.columns)
    try:
        idx = cols.index(after_col)
    except ValueError:
        df[new_col] = series
        return df
    left = cols[: idx + 1]
    right = cols[idx + 1 :]
    df[new_col] = series
    return df[left + [new_col] + right]


def aggregate(out_path: str, column_name: str, sources: List[Source], sheet_name: str, engine: str = "xlsxwriter", add_extra_column: bool = True, dk_entries_path: Optional[str] = None) -> Tuple[int, pd.DataFrame]:
    parts: List[pd.DataFrame] = []
    for s in sources:
        df = _read_lineups(s.path, sheet_name)
        if df is None or df.empty:
            continue
        if "Rank" in df.columns:
            df = df.drop(columns=["Rank"])  # type: ignore
        df["Projection"] = pd.to_numeric(df["Projection"], errors="coerce")
        df = df.dropna(subset=["Projection"])  # type: ignore
        if add_extra_column:
            # Avoid duplicate column names from prior aggregations
            if column_name in df.columns:
                df = df.rename(columns={column_name: f"{column_name}_orig"})
            df[column_name] = s.value
            if "Game Stack" in df.columns:
                df = _insert_after(df, column_name, df[column_name], "Game Stack")
        parts.append(df)

    if not parts:
        print("No input sheets found; nothing to aggregate", file=sys.stderr)
        empty = pd.DataFrame()
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with pd.ExcelWriter(out_path, engine=engine) as writer:
            empty.to_excel(writer, sheet_name, index=False)
        return 0, empty

    combined = pd.concat(parts, axis=0, ignore_index=True)
    combined = combined.sort_values(by=["Projection"], ascending=False, kind="mergesort").reset_index(drop=True)
    combined["Rank"] = range(1, len(combined) + 1)
    cols = list(combined.columns)
    if "Rank" in cols:
        cols.remove("Rank")
        cols = ["Rank"] + cols
        combined = combined[cols]

    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(out_path, engine=engine) as writer:
        combined.to_excel(writer, sheet_name, index=False)
        # Attempt to write DK Lineups tab using DK entries mapping
        try:
            if dk_entries_path:
                dk_entries = load_dk_entries(dk_entries_path)
            else:
                dk_entries = load_dk_entries()
            # For aggregation we don't have projections_df here; build a minimal frame with Name/Position/Team if present
            # Heuristic: extract base names from player columns and construct a frame with Name only
            player_cols = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"] if c in combined.columns or f"{c}_orig" in combined.columns]
            proj_min = pd.DataFrame({"Name": []})
            if player_cols:
                # Collect names from combined by stripping trailing parentheticals
                def _extract(value: object) -> str:
                    s = str(value)
                    if s.endswith(")") and "(" in s:
                        try:
                            return s.rsplit(" (", 1)[0]
                        except Exception:
                            return s
                    return s
                names_series = pd.Series(dtype=object)
                # Build a DK formatting source where player columns are uniquely named
                dk_source = combined.copy()
                # If an extra label column conflicts with a player slot (e.g., QB), temporarily rename it
                if "QB" in dk_source.columns and "QB_orig" in dk_source.columns:
                    dk_source = dk_source.rename(columns={"QB_orig": "QB", "QB": "QB Label"})
                for base in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]:
                    col = base if base in dk_source.columns else (f"{base}_orig" if f"{base}_orig" in dk_source.columns else None)
                    if not col:
                        continue
                    names_series = pd.concat([names_series, dk_source[col].dropna().astype(str).map(_extract)], ignore_index=True)
                unique_names = sorted(set(n for n in names_series.tolist() if n))
                proj_min = pd.DataFrame({"Name": unique_names})
            # Use the DK source with uniquely named player columns for formatting
            if 'dk_source' not in locals():
                dk_source = combined.copy()
            dk_tab = format_lineups_for_dk(dk_source, proj_min, dk_entries)
            dk_tab.to_excel(writer, "DK Lineups", index=False)
        except Exception as e:
            print(f"Warning: failed to write DK Lineups sheet: {e}", file=sys.stderr)
        try:
            # Pick the last matching column name to avoid ambiguity if duplicates exist
            matching_cols = [i for i, c in enumerate(combined.columns) if c == column_name]
            if not matching_cols:
                raise ValueError(f"Missing column '{column_name}' in combined data")
            series = combined.iloc[:, matching_cols[-1]]
            summary = (
                series.astype(object)
                .fillna("")
                .value_counts(dropna=False)
                .reset_index()
                .rename(columns={"index": column_name, column_name: "Lineups"})
            )
            summary = summary.sort_values(by=["Lineups", column_name], ascending=[False, True])
            summary.to_excel(writer, "Summary", index=False)
        except Exception as e:
            print(f"Warning: failed to write Summary sheet: {e}", file=sys.stderr)

    return len(combined), combined


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    sources = _parse_sources(args.src)
    total, _ = aggregate(
        args.out,
        args.column_name,
        sources,
        args.sheet,
        args.engine,
        add_extra_column=(not args.no_extra_column),
        dk_entries_path=args.dk_entries,
    )
    print(f"Aggregated {total} lineups into {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


