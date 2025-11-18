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
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd  # type: ignore
import yaml  # type: ignore

# Ensure project root on sys.path so `tools` and `src` can be imported when invoked from anywhere
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from tools.aggregate_lineups import aggregate, Source as AggSource  # type: ignore
from src.dk_upload import load_dk_entries, format_lineups_for_dk  # type: ignore
from src.constraints import parse_rules_mapping  # type: ignore


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
	p.add_argument("--showdown", action="store_true", help="Use showdown YAML (src/contests-showdown.yaml)")
	return p.parse_args()


def _contests_yaml_path(showdown: bool) -> Path:
	return PROJECT_ROOT / "src" / ("contests-showdown.yaml" if showdown else "contests.yaml")


def ensure_inputs(showdown: bool) -> None:
	if not DK_ENTRIES_PATH.exists():
		_fail(f"Missing required DK entries file: {DK_ENTRIES_PATH}")
	ss_files = glob.glob(str(DATA_DIR / "NFL_*.csv"))
	if not ss_files:
		_fail(f"Missing SaberSim projections; place at least one file matching {DATA_DIR/'NFL_*.csv'}")
	yaml_path = _contests_yaml_path(showdown)
	if not yaml_path.exists():
		_fail(f"Missing contests YAML at {yaml_path}")


def run_get_contests(date_str: str, showdown: bool) -> None:
	cmd = [_pybin(), str(PROJECT_ROOT / "scripts" / "get_contests.py"), date_str]
	if showdown:
		cmd.append("--showdown")
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


def read_yaml_runs(yaml_path: Path) -> Dict[str, List[Dict[str, Any]]]:
	with open(yaml_path, "r", encoding="utf-8") as f:
		yml = yaml.safe_load(f) or {}
	if not isinstance(yml, dict):
		_fail(f"Unexpected YAML structure in {yaml_path}")

	out: Dict[str, List[Dict[str, Any]]] = {}
	for label, cfg in yml.items():
		if not isinstance(cfg, dict):
			continue

		# New-style: per-label `constraints` with optional `runs` list and defaults
		constraints = cfg.get("constraints", {})
		runs_list: List[Dict[str, Any]] = []
		if isinstance(constraints, dict):
			# Validate showdown rules eagerly if present
			rules_raw = constraints.get("rules")
			if isinstance(rules_raw, dict):
				try:
					parse_rules_mapping(rules_raw)
				except Exception as exc:
					_fail(f"Invalid showdown constraint rules for '{label}' in {yaml_path}: {exc}")

			global_defaults = {
				k: v
				for k, v in constraints.items()
				if k not in {"runs", "rules"}
			}
			raw_runs = constraints.get("runs") or []
			if isinstance(raw_runs, list):
				for run_cfg in raw_runs:
					if isinstance(run_cfg, dict):
						merged: Dict[str, Any] = dict(global_defaults)
						merged.update(run_cfg)
						runs_list.append(merged)

		# Backwards-compatible: fall back to legacy run_N strings if no structured runs
		if not runs_list:
			legacy_runs = {
				k: v
				for k, v in cfg.items()
				if isinstance(k, str) and k.startswith("run_") and isinstance(v, str)
			}
			if legacy_runs:
				# Preserve ordering by run_1, run_2, ...
				def _run_key(k: str) -> Tuple[int, str]:
					try:
						return (int(k.split("_", 1)[1]), k)
					except Exception:
						return (999999, k)

				for key in sorted(legacy_runs.keys(), key=_run_key):
					runs_list.append({"_legacy": legacy_runs[key]})

		if runs_list:
			out[label] = runs_list

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


def bundle_for_label(ts: str, label: str, runs: List[Dict[str, Any]]) -> BundleResult:
	_log(f"Bundling runs for '{label}'")
	if not runs:
		_fail(f"No runs defined in YAML for '{label}'")
	base_intermediate = OUTPUT_DIR / ts / "bundle" / "intermediate" / label
	base_intermediate.mkdir(parents=True, exist_ok=True)
	sources: List[Tuple[Path, str]] = []

	def _bool_env_value(val: Any) -> Optional[str]:
		if isinstance(val, bool):
			return "1" if val else None
		if val is None:
			return None
		s = str(val).strip().lower()
		if s in {"1", "true", "yes", "on", "enable"}:
			return "1"
		return None

	for idx, run_cfg in enumerate(runs, start=1):
		run_token = f"Run{idx}"
		run_dir = base_intermediate / run_token
		run_dir.mkdir(parents=True, exist_ok=True)

		env = os.environ.copy()
		env["OUTDIR"] = str(run_dir)
		# For showdown runs, propagate the field-size label so src.cli can load
		# label-specific showdown rules from the contests-showdown.yaml file.
		env["DFS_SHOWDOWN_FIELD_SIZE_LABEL"] = label

		# Legacy path: run_cfg provides a raw command string
		if "_legacy" in run_cfg:
			args = _extract_run_args(str(run_cfg["_legacy"]))
			cmd = ["bash", "run.sh", *args]
			_log(f"Executing ({label}/{run_token}) [legacy]: {' '.join(cmd)}")
			subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=False)
		else:
			# Structured path: build env vars for run.sh based on config
			# Core numeric parameters
			if "lineups" in run_cfg:
				env["LINEUPS"] = str(run_cfg["lineups"])
			if "min_salary" in run_cfg:
				env["MIN_SALARY"] = str(run_cfg["min_salary"])
			if "max_salary" in run_cfg:
				env["MAX_SALARY"] = str(run_cfg["max_salary"])
			if "stack" in run_cfg:
				env["STACK"] = str(run_cfg["stack"])
			if "game_stack" in run_cfg:
				env["GAME_STACK"] = str(run_cfg["game_stack"])
			if "game_stack_target" in run_cfg:
				env["GAME_STACK_TARGET"] = str(run_cfg["game_stack_target"])

			# Ownership / projection thresholds
			key_map = {
				"min_sum_projection": "MIN_SUM_PROJECTION",
				"max_sum_projection": "MAX_SUM_PROJECTION",
				"min_sum_ownership": "MIN_SUM_OWNERSHIP",
				"max_sum_ownership": "MAX_SUM_OWNERSHIP",
				"min_product_ownership": "MIN_PRODUCT_OWNERSHIP",
				"max_product_ownership": "MAX_PRODUCT_OWNERSHIP",
				"min_weighted_ownership": "MIN_WEIGHTED_OWNERSHIP",
				"max_weighted_ownership": "MAX_WEIGHTED_OWNERSHIP",
			}
			for yaml_key, env_key in key_map.items():
				if yaml_key in run_cfg and run_cfg[yaml_key] is not None:
					env[env_key] = str(run_cfg[yaml_key])

			# Booleans toggles
			if _bool_env_value(run_cfg.get("allow_qb_vs_dst")):
				env["ALLOW_QB_VS_DST"] = "1"
			if _bool_env_value(run_cfg.get("allow_rb_vs_dst")):
				env["ALLOW_RB_VS_DST"] = "1"
			if _bool_env_value(run_cfg.get("rb_dst_stack")):
				env["RB_DST_STACK"] = "1"
			if _bool_env_value(run_cfg.get("bringback")):
				env["BRINGBACK"] = "1"

			# Projections / mode
			projections = str(run_cfg.get("projections", "")).strip().lower()
			if projections == "sabersim":
				# Use SaberSim projections (classic) or showdown SaberSim CSV
				env["SABERSIM"] = "1"
			elif projections:
				# Treat as explicit projections path
				env["PROJECTIONS"] = projections

			mode = str(run_cfg.get("mode", "")).strip().lower()
			if mode == "showdown":
				env["SHOWDOWN"] = "1"

			cmd = ["bash", "run.sh"]
			_log(f"Executing ({label}/{run_token}) [structured]: {' '.join(cmd)} with env overrides")
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
	for col in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST", "CPT", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"]:
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
	is_showdown = "CPT" in df_dk.columns or "FLEX1" in df_dk.columns
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
		if is_showdown:
			rec = {
				"CPT": row.get("CPT", ""),
				"FLEX1": row.get("FLEX1", row.get("FLEX", "")),
				"FLEX2": row.get("FLEX2", ""),
				"FLEX3": row.get("FLEX3", ""),
				"FLEX4": row.get("FLEX4", ""),
				"FLEX5": row.get("FLEX5", ""),
			}
		else:
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
			if is_showdown:
				out_rows.append(
					{
						"Entry ID": crow.get("Entry ID", ""),
						"Contest Name": crow.get("Contest Name", ""),
						"Contest ID": crow.get("Contest ID", ""),
						"Entry Fee": crow.get("Entry Fee", ""),
						"CPT": lrow["CPT"],
						"FLEX1": lrow["FLEX1"],
						"FLEX2": lrow["FLEX2"],
						"FLEX3": lrow["FLEX3"],
						"FLEX4": lrow["FLEX4"],
						"FLEX5": lrow["FLEX5"],
					}
				)
			else:
				out_rows.append(
					{
						"Entry ID": crow.get("Entry ID", ""),
						"Contest Name": crow.get("Contest Name", ""),
						"Contest ID": crow.get("Contest ID", ""),
						"Entry Fee": crow.get("Entry Fee", ""),
						"QB": lrow["QB"],
						"RB": lrow["RB1"],
						"RB.1": lrow["RB2"],
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
	# Build DataFrame with exact header order
	# Note: pandas will prevent exact duplicate column names; we use suffixes for the second RB and WR columns,
	# then rename to duplicate names when writing CSV via manual writer to preserve headers exactly.
	df_out = pd.DataFrame(out_rows)
	# Compose the final header order including duplicates
	if is_showdown:
		final_headers = [
			"Entry ID",
			"Contest Name",
			"Contest ID",
			"Entry Fee",
			"CPT",
			"FLEX1",
			"FLEX2",
			"FLEX3",
			"FLEX4",
			"FLEX5",
		]
	else:
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
		if is_showdown:
			# Showdown header: duplicate FLEX column names as required by DK
			writer.writerow(
				[
					"Entry ID",
					"Contest Name",
					"Contest ID",
					"Entry Fee",
					"CPT",
					"FLEX",
					"FLEX",
					"FLEX",
					"FLEX",
					"FLEX",
				]
			)
			for _, r in df_out[final_headers].iterrows():
				writer.writerow(
					[
						r["Entry ID"],
						r["Contest Name"],
						r["Contest ID"],
						r["Entry Fee"],
						r["CPT"],
						r["FLEX1"],
						r["FLEX2"],
						r["FLEX3"],
						r["FLEX4"],
						r["FLEX5"],
					]
				)
		else:
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
	yaml_path = _contests_yaml_path(args.showdown)
	yaml_name = yaml_path.name
	# Expose showdown rules path to downstream runs (used by src.cli in showdown mode)
	if args.showdown:
		os.environ["DFS_SHOWDOWN_RULES_PATH"] = str(yaml_path)
	ensure_inputs(args.showdown)
	# Step 2: contests + classification
	run_get_contests(args.date, args.showdown)
	entries_classified_df, quotas, present_labels = load_classification_info()
	_log(f"Field sizes present: {present_labels} | quotas={quotas}")
	# Step 3: bundle per label present
	yaml_runs = read_yaml_runs(yaml_path)
	files_by_label: Dict[str, Path] = {}
	source_to_label: Dict[str, str] = {}
	for label in present_labels:
		if label not in yaml_runs:
			_log(f"Warning: label '{label}' not found in {yaml_name}; skipping")
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


