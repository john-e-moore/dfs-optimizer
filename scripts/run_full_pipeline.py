#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd  # type: ignore
import yaml  # type: ignore

# Ensure project root on sys.path so `tools` and `src` can be imported when invoked from anywhere
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from tools.aggregate_lineups import aggregate, Source as AggSource  # type: ignore
from src.dk_upload import load_dk_entries, format_lineups_for_dk  # type: ignore


DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
CONTESTS_YAML_PATH = PROJECT_ROOT / "src" / "contests.yaml"
DK_ENTRIES_PATH = DATA_DIR / "DKEntries.csv"
DK_ENTRIES_CLASSIFIED_PATH = DATA_DIR / "DKEntriesClassified.csv"


def _pybin() -> str:
	# Prefer venv python if available
	venv = PROJECT_ROOT / "venv" / "bin" / "python"
	return str(venv) if venv.exists() and os.access(venv, os.X_OK) else sys.executable


def _log(msg: str) -> None:
	now = datetime.now().strftime("%H:%M:%S")
	print(f"[{now}] {msg}")


def _fail(msg: str, code: int = 1) -> None:
	_log(f"ERROR: {msg}")
	sys.exit(code)


def parse_args() -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Run full DFS pipeline to produce DK-uploadable CSV")
	p.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD (used by scripts/get_contests.py)")
	p.add_argument("--random-seed", type=int, default=None, help="Optional seed for diversification")
	return p.parse_args()


def ensure_inputs() -> None:
	if not DK_ENTRIES_PATH.exists():
		_fail(f"Missing required DK entries file: {DK_ENTRIES_PATH}")
	ss_files = glob.glob(str(DATA_DIR / "NFL_*.csv"))
	if not ss_files:
		_fail(f"Missing SaberSim projections; place at least one file matching {DATA_DIR/'NFL_*.csv'}")
	if not CONTESTS_YAML_PATH.exists():
		_fail(f"Missing contests.yaml at {CONTESTS_YAML_PATH}")


def run_get_contests(date_str: str) -> None:
	cmd = [_pybin(), str(PROJECT_ROOT / "scripts" / "get_contests.py"), date_str]
	_log(f"Downloading and classifying contests: {' '.join(cmd)}")
	try:
		subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
	except subprocess.CalledProcessError as e:
		_fail(f"get_contests failed with exit code {e.returncode}")
	if not DK_ENTRIES_CLASSIFIED_PATH.exists():
		_fail(f"Expected output not found: {DK_ENTRIES_CLASSIFIED_PATH}")


def load_classification_info() -> Tuple[pd.DataFrame, Dict[str, int], List[str]]:
	df = pd.read_csv(DK_ENTRIES_CLASSIFIED_PATH)
	if "field_size_classification" not in df.columns:
		_fail("DKEntriesClassified.csv missing 'field_size_classification'")
	# Normalize labels to strings; treat empty/NaN as missing
	df["field_size_classification"] = df["field_size_classification"].astype(str).fillna("").map(lambda s: s.strip())
	df = df[df["field_size_classification"] != ""].copy()
	if df.empty:
		_fail("No classified entries found (field_size_classification empty for all rows)")
	# Maintain stable order by original CSV for later contest assignment
	present_labels: List[str] = []
	for lbl in df["field_size_classification"].tolist():
		if lbl not in present_labels:
			present_labels.append(lbl)
	quotas: Dict[str, int] = df["field_size_classification"].value_counts().to_dict()  # type: ignore
	return df, quotas, present_labels


def read_yaml_runs() -> Dict[str, Dict[str, str]]:
	with open(CONTESTS_YAML_PATH, "r", encoding="utf-8") as f:
		yml = yaml.safe_load(f) or {}
	if not isinstance(yml, dict):
		_fail(f"Unexpected YAML structure in {CONTESTS_YAML_PATH}")
	# Keep sections: each label maps to dict of run_* plus thresholds
	out: Dict[str, Dict[str, str]] = {}
	for label, cfg in yml.items():
		if not isinstance(cfg, dict):
			continue
		runs = {k: v for k, v in cfg.items() if isinstance(k, str) and k.startswith("run_") and isinstance(v, str)}
		if runs:
			out[label] = runs
	return out


def _extract_run_args(run_value: str) -> List[str]:
	# Expect strings like: "bash run.sh --ss --lineups 200 ..."
	tokens = shlex.split(run_value)
	if not tokens:
		return []
	# Drop leading "bash" and "run.sh" if present
	if tokens[0] == "bash":
		tokens = tokens[1:]
	if tokens and tokens[0].endswith("run.sh"):
		tokens = tokens[1:]
	return tokens


def _find_latest_child_output(run_dir: Path) -> Optional[Path]:
	# Discover newest subdirectory containing lineups.xlsx
	if not run_dir.exists():
		return None
	children = [p for p in run_dir.glob("*/") if p.is_dir()]
	children.sort(key=lambda p: p.stat().st_mtime, reverse=True)
	for c in children:
		out_xlsx = c / "lineups.xlsx"
		if out_xlsx.exists():
			return out_xlsx
	# Fallback: maybe run.sh wrote directly under run_dir
	fallback = run_dir / "lineups.xlsx"
	return fallback if fallback.exists() else None


@dataclass
class BundleResult:
	label: str
	outfile: Path
	sources: List[Tuple[Path, str]]


def bundle_for_label(ts: str, label: str, run_map: Dict[str, str]) -> BundleResult:
	_log(f"Bundling runs for '{label}'")
	# Order runs by run_1, run_2, ...
	def _run_key(k: str) -> Tuple[int, str]:
		try:
			return (int(k.split("_", 1)[1]), k)
		except Exception:
			return (999999, k)
	ordered = [k for k in sorted(run_map.keys(), key=_run_key)]
	if not ordered:
		_fail(f"No runs defined in YAML for '{label}'")
	base_intermediate = OUTPUT_DIR / ts / "bundle" / "intermediate" / label
	base_intermediate.mkdir(parents=True, exist_ok=True)
	sources: List[Tuple[Path, str]] = []
	for idx, key in enumerate(ordered, start=1):
		args = _extract_run_args(run_map[key])
		run_token = f"Run{idx}"
		run_dir = base_intermediate / run_token
		run_dir.mkdir(parents=True, exist_ok=True)
		env = os.environ.copy()
		env["OUTDIR"] = str(run_dir)
		cmd = ["bash", "run.sh", *args]
		_log(f"Executing ({label}/{run_token}): {' '.join(cmd)}")
		subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=False)
		out_xlsx = _find_latest_child_output(run_dir)
		if out_xlsx and out_xlsx.exists():
			sources.append((out_xlsx, run_token))
			_log(f"Collected: {out_xlsx}")
		else:
			_log(f"Warning: missing output for {label}/{run_token} expected at {run_dir}/*/lineups.xlsx")
	if not sources:
		_fail(f"No sources collected for '{label}' (no lineups.xlsx found in any run)")
	outfile = OUTPUT_DIR / ts / f"{label}.xlsx"
	# Aggregate using tools.aggregate_lineups
	agg_sources = [AggSource(path=str(p), value=v) for (p, v) in sources]
	total, _combined = aggregate(
		str(outfile),
		"Bundle",
		agg_sources,
		sheet_name="Lineups",
		engine="xlsxwriter",
		add_extra_column=True,
		dk_entries_path=str(DK_ENTRIES_PATH),
	)
	if total == 0:
		_fail(f"Aggregated 0 lineups for '{label}'")
	_log(f"Bundled {total} lineups -> {outfile}")
	return BundleResult(label=label, outfile=outfile, sources=sources)


def diversify(ts: str, files_by_label: Dict[str, Path], quotas: Dict[str, int], seed: Optional[int]) -> Path:
	out_path = OUTPUT_DIR / ts / "diversified.xlsx"
	cmd: List[str] = [_pybin(), "-m", "src.feature_diversify.cli"]
	# Inputs
	for _, fpath in files_by_label.items():
		cmd += ["--input", str(fpath)]
	# Picks (explicit sheet name)
	for label, fpath in files_by_label.items():
		count = int(quotas.get(label, 0))
		if count > 0:
			cmd += ["--pick", f"{str(fpath)}:Lineups:{count}"]
	if seed is not None:
		cmd += ["--random-seed", str(seed)]
	cmd += ["--out", str(out_path)]
	_log(f"Diversifying: {' '.join(cmd)}")
	subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
	if not out_path.exists():
		_fail(f"Expected diversified output not found: {out_path}")
	return out_path


def read_diversified_for_upload(diversified_path: Path) -> pd.DataFrame:
	# Prefer DK Lineups; fall back to Selected and format via dk_upload
	try:
		df = pd.read_excel(diversified_path, sheet_name="DK Lineups")
		return df
	except Exception:
		pass
	selected = pd.read_excel(diversified_path, sheet_name="Selected")
	dk_entries_df = load_dk_entries(str(DK_ENTRIES_PATH))
	# Minimal projections frame for IDs (names only)
	names: List[str] = []
	for col in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]:
		if col in selected.columns:
			names.extend([str(v) for v in selected[col].dropna().astype(str).tolist()])
	unique_names = sorted(set(names))
	proj_min = pd.DataFrame({"Name": unique_names})
	df_dk = format_lineups_for_dk(selected, proj_min, dk_entries_df)
	return df_dk


def build_upload_csv(
	ts: str,
	diversified_path: Path,
	entries_classified_df: pd.DataFrame,
	label_by_source_file: Dict[str, str],
) -> Path:
	df_dk = read_diversified_for_upload(diversified_path)
	# Ensure necessary player columns exist (renames)
	col_map = {
		"RB1": "RB1",
		"RB2": "RB2",
		"WR1": "WR1",
		"WR2": "WR2",
		"WR3": "WR3",
	}
	# Build list of selected rows, grouped by classification using Source File
	if "Source File" not in df_dk.columns:
		_fail("Diversified workbook missing 'Source File' column; cannot map selected lineups back to field size")
	# Keep selection order stable
	if "Rank" in df_dk.columns:
		df_dk = df_dk.sort_values(by=["Rank"], ascending=True, kind="mergesort").reset_index(drop=True)
	# Create mapping label -> list of lineup dicts
	selected_by_label: Dict[str, List[dict]] = {}
	for _, row in df_dk.iterrows():
		src_file = str(row.get("Source File", "")).strip()
		label = label_by_source_file.get(src_file)
		if not label:
			# Try to normalize path (resolve)
			try:
				label = label_by_source_file.get(str(Path(src_file).resolve()))
			except Exception:
				label = None
		if not label:
			continue
		rec = {
			"QB": row.get("QB", ""),
			"RB1": row.get("RB1", row.get("RB", "")),
			"RB2": row.get("RB2", ""),
			"WR1": row.get("WR1", row.get("WR", "")),
			"WR2": row.get("WR2", ""),
			"WR3": row.get("WR3", ""),
			"TE": row.get("TE", ""),
			"FLEX": row.get("FLEX", ""),
			"DST": row.get("DST", ""),
		}
		selected_by_label.setdefault(label, []).append(rec)
	# Prepare contest rows per classification in original order
	required_cols = ["Entry ID", "Contest Name", "Contest ID", "Entry Fee"]
	for c in required_cols:
		if c not in entries_classified_df.columns:
			_fail(f"'data/DKEntries.csv' is missing required column in classified output: {c}")
	out_rows: List[dict] = []
	for label in selected_by_label.keys():
		contests = entries_classified_df[entries_classified_df["field_size_classification"] == label]
		contests = contests.reset_index(drop=True)
		lineups = selected_by_label.get(label, [])
		if len(lineups) < len(contests):
			_fail(f"Not enough selected lineups for '{label}': need {len(contests)}, have {len(lineups)}")
		for i in range(len(contests)):
			crow = contests.iloc[i]
			lrow = lineups[i]
			out_rows.append(
				{
					"Entry ID": crow.get("Entry ID", ""),
					"Contest Name": crow.get("Contest Name", ""),
					"Contest ID": crow.get("Contest ID", ""),
					"Entry Fee": crow.get("Entry Fee", ""),
					"QB": lrow["QB"],
					"RB": lrow["RB1"],
					"RB.1": lrow["RB2"],  # second RB duplicate column label disambiguated on CSV write/read
					"WR": lrow["WR1"],
					"WR.1": lrow["WR2"],
					"WR.2": lrow["WR3"],
					"TE": lrow["TE"],
					"FLEX": lrow["FLEX"],
					"DST": lrow["DST"],
				}
			)
	if not out_rows:
		_fail("No output rows produced for upload CSV")
	# Build DataFrame with exact first 13 columns in order
	# Note: pandas will prevent exact duplicate column names; we use suffixes for the second RB and WR columns,
	# then rename to duplicate names when writing CSV via manual writer to preserve headers exactly.
	df_out = pd.DataFrame(out_rows)
	# Compose the final header order including duplicates
	final_headers = [
		"Entry ID",
		"Contest Name",
		"Contest ID",
		"Entry Fee",
		"QB",
		"RB",
		"RB.1",
		"WR",
		"WR.1",
		"WR.2",
		"TE",
		"FLEX",
		"DST",
	]
	out_path = OUTPUT_DIR / ts / "DKEntries.csv"
	out_path.parent.mkdir(parents=True, exist_ok=True)
	# Write CSV with exact header names requested:
	with open(out_path, "w", encoding="utf-8", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(
			[
				"Entry ID",
				"Contest Name",
				"Contest ID",
				"Entry Fee",
				"QB",
				"RB",
				"RB",
				"WR",
				"WR",
				"WR",
				"TE",
				"FLEX",
				"DST",
			]
		)
		for _, r in df_out[final_headers].iterrows():
			writer.writerow(
				[
					r["Entry ID"],
					r["Contest Name"],
					r["Contest ID"],
					r["Entry Fee"],
					r["QB"],
					r["RB"],
					r["RB.1"],
					r["WR"],
					r["WR.1"],
					r["WR.2"],
					r["TE"],
					r["FLEX"],
					r["DST"],
				]
			)
	return out_path


def main() -> int:
	args = parse_args()
	# Shared timestamp across all outputs
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	ensure_inputs()
	# Step 2: contests + classification
	run_get_contests(args.date)
	entries_classified_df, quotas, present_labels = load_classification_info()
	_log(f"Field sizes present: {present_labels} | quotas={quotas}")
	# Step 3: bundle per label present
	yaml_runs = read_yaml_runs()
	files_by_label: Dict[str, Path] = {}
	source_to_label: Dict[str, str] = {}
	for label in present_labels:
		if label not in yaml_runs:
			_log(f"Warning: label '{label}' not found in contests.yaml; skipping")
			continue
		res = bundle_for_label(ts, label, yaml_runs[label])
		files_by_label[label] = res.outfile
		# Map the absolute path string used by diversify's 'Source File' back to label
		abs_outfile = str(res.outfile.resolve())
		source_to_label[abs_outfile] = label
		source_to_label[str(res.outfile)] = label
	# Ensure we have at least one file
	if not files_by_label:
		_fail("No bundles produced for any present field size")
	# Step 4: diversify
	diversified_path = diversify(ts, files_by_label, quotas, args.random_seed)
	# Step 5: compose upload CSV
	out_csv = build_upload_csv(ts, diversified_path, entries_classified_df, source_to_label)
	_log(f"DraftKings upload CSV written: {out_csv}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())


