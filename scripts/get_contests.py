#!/usr/bin/env python3
"""
Download DraftKings contest data for a given date, enrich local DK entries with
number of entrants and field-size classification, and write the classified CSV.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3  # type: ignore
import pandas as pd  # type: ignore
import yaml  # type: ignore
from botocore.exceptions import ClientError  # type: ignore


DATA_DIR = Path("data")
CONTESTS_JSON_LOCAL = DATA_DIR / "contests.json"
DK_ENTRIES_CSV = DATA_DIR / "DKEntries.csv"
DK_ENTRIES_CLASSIFIED_CSV = DATA_DIR / "DKEntriesClassified.csv"
CONTESTS_YAML_PATH = Path("src") / "contests.yaml"


@dataclass(frozen=True)
class AwsLocation:
    bucket: str
    prefix: str
    region: str

    def key_for_contests(self, date_str: str) -> str:
        # s3://{bucket}/{prefix}/{date}/nfl/contests.json
        normalized_prefix = self.prefix.strip().strip("/")
        return f"{normalized_prefix}/{date_str}/nfl/contests.json"

    def key_for_slate(self, date_str: str, slate_id: str) -> str:
        # s3://{bucket}/{prefix}/{date}/nfl/{dg}.json
        normalized_prefix = self.prefix.strip().strip("/")
        return f"{normalized_prefix}/{date_str}/nfl/{slate_id}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download contests, classify DKEntries by field size, and write DKEntriesClassified.csv"
    )
    parser.add_argument(
        "date",
        help="Slate date in YYYY-MM-DD format",
    )
    return parser.parse_args()


def validate_date(date_str: str) -> None:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"Invalid date '{date_str}'. Expected format YYYY-MM-DD.") from exc


def read_env_location() -> AwsLocation:
    bucket = os.getenv("DK_CONTESTS_S3_BUCKET", "").strip()
    prefix = os.getenv("DK_CONTESTS_S3_PREFIX", "").strip()
    region = os.getenv("DK_CONTESTS_AWS_REGION", "us-east-2").strip() or "us-east-2"
    if not bucket or not prefix:
        raise SystemExit(
            "Missing required environment variables: DK_CONTESTS_S3_BUCKET and/or DK_CONTESTS_S3_PREFIX."
        )
    return AwsLocation(bucket=bucket, prefix=prefix, region=region)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_s3_object(
    s3_client: Any,
    bucket: str,
    key: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        s3_client.download_file(bucket, key, str(destination))
    except ClientError as exc:
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        raise SystemExit(f"Failed to download s3://{bucket}/{key} -> {destination}: {error_message}") from exc


def normalize_contest_id(value: Any) -> Optional[str]:
    """
    Normalize contest IDs to a clean string without trailing decimals.
    Returns None if value is missing.
    """
    if pd.isna(value):
        return None
    # Handle numeric types
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        # Safely drop .0 if present
        if value.is_integer():
            return str(int(value))
        return str(value)
    # Strings
    s = str(value).strip()
    # Remove trailing .0 if present (common when csv was parsed as float)
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def load_contests_frame(contests_path: Path) -> pd.DataFrame:
    with contests_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    # Handle either a top-level list or an object with "Contests" list
    if isinstance(payload, list):
        contests_list = payload
    elif isinstance(payload, dict) and isinstance(payload.get("Contests"), list):
        contests_list = payload["Contests"]
    else:
        raise SystemExit(
            f"Unexpected contests.json structure at {contests_path}; expected a list or a dict with 'Contests' list."
        )

    records: List[Dict[str, Any]] = []
    for obj in contests_list:
        if not isinstance(obj, dict):
            continue
        _id = normalize_contest_id(obj.get("id"))
        if _id is None:
            continue
        records.append(
            {
                "id": _id,
                "m": obj.get("m"),  # number of entrants
                "dg": obj.get("dg"),  # slate id
            }
        )
    return pd.DataFrame.from_records(records)


def read_entries_first_14_columns(entries_path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(entries_path, usecols=range(14))
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing input file: {entries_path}") from exc
    if "Contest ID" not in df.columns:
        raise SystemExit("Expected 'Contest ID' column in DKEntries.csv (with header).")
    # Normalize IDs on the entries side
    df["Contest ID"] = df["Contest ID"].map(normalize_contest_id)
    return df


def compute_unique_slate_id(merged: pd.DataFrame) -> str:
    # Only consider rows where we matched a contest (dg not null) and normalize ids
    raw_values = merged["dg"].dropna().tolist() if "dg" in merged.columns else []
    normalized_values: List[str] = []
    for v in raw_values:
        nv = normalize_contest_id(v)
        if nv and nv.lower() != "nan" and nv not in normalized_values:
            normalized_values.append(nv)
    if len(normalized_values) != 1:
        # Produce a small diagnostic summary
        value_counts = (
            merged["dg"]
            .dropna()
            .astype(str)
            .value_counts()
            .to_dict()
            if "dg" in merged.columns
            else {}
        )
        raise SystemExit(
            f"Expected exactly one slate id (dg) across matched contests; found: {normalized_values or 'none'} "
            f"with counts {value_counts}. Ensure all contests are from the same slate."
        )
    return normalized_values[0]


def classify_field_size(num_entrants: Optional[float], thresholds: Dict[str, Dict[str, Any]]) -> str:
    if num_entrants is None or pd.isna(num_entrants):
        return ""
    try:
        entrants_int = int(num_entrants)
    except Exception:
        return ""
    for label, cfg in thresholds.items():
        min_e = int(cfg.get("min_entrants", -1))
        max_e = int(cfg.get("max_entrants", -1))
        if min_e <= entrants_int <= max_e:
            return label
    return ""


def load_classification_thresholds(yaml_path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing classification YAML at {yaml_path}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Unexpected YAML structure in {yaml_path}; expected a mapping")
    # Keep only sections that include the min/max fields
    thresholds: Dict[str, Dict[str, Any]] = {}
    for label, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        if "min_entrants" in cfg and "max_entrants" in cfg:
            thresholds[label] = cfg
    if not thresholds:
        raise SystemExit(f"No classification ranges with min_entrants/max_entrants found in {yaml_path}")
    return thresholds


def main() -> None:
    args = parse_args()
    validate_date(args.date)
    aws = read_env_location()
    ensure_data_dir()

    # Initialize S3 client
    s3_client = boto3.client("s3", region_name=aws.region)

    # 1) Download contests.json
    contests_key = aws.key_for_contests(args.date)
    print(f"Downloading contests: s3://{aws.bucket}/{contests_key} -> {CONTESTS_JSON_LOCAL}")
    download_s3_object(s3_client, aws.bucket, contests_key, CONTESTS_JSON_LOCAL)

    # 2) Read entries (first 14 columns)
    entries_df = read_entries_first_14_columns(DK_ENTRIES_CSV)
    original_columns: List[str] = list(entries_df.columns)

    # 3) Load contests and merge
    contests_df = load_contests_frame(CONTESTS_JSON_LOCAL)
    if contests_df.empty:
        raise SystemExit(f"No contests found in {CONTESTS_JSON_LOCAL}")
    merged_df = entries_df.merge(
        contests_df[["id", "m", "dg"]],
        how="left",
        left_on="Contest ID",
        right_on="id",
    )
    # 4) Add num_entrants
    merged_df["num_entrants"] = merged_df["m"]

    # 5) Validate single slate id and download slate JSON
    slate_id = compute_unique_slate_id(merged_df)
    slate_file_local = DATA_DIR / f"{slate_id}.json"
    slate_key = aws.key_for_slate(args.date, slate_id)
    print(f"Downloading slate: s3://{aws.bucket}/{slate_key} -> {slate_file_local}")
    download_s3_object(s3_client, aws.bucket, slate_key, slate_file_local)

    # 6) Classification
    thresholds = load_classification_thresholds(CONTESTS_YAML_PATH)
    merged_df["field_size_classification"] = merged_df["num_entrants"].map(
        lambda v: classify_field_size(v, thresholds)
    )

    # 7) Output: keep original columns first, then append new ones
    output_columns: List[str] = list(original_columns) + ["num_entrants", "field_size_classification"]
    # Ensure columns exist even if originals didn't include them (robustness)
    for col in ["num_entrants", "field_size_classification"]:
        if col not in merged_df.columns:
            merged_df[col] = ""
    print(f"Writing classified entries -> {DK_ENTRIES_CLASSIFIED_CSV}")
    merged_df.to_csv(DK_ENTRIES_CLASSIFIED_CSV, index=False, columns=output_columns)

    # Summary
    matched_count = int(merged_df["id"].notna().sum()) if "id" in merged_df.columns else 0
    classification_counts = (
        merged_df["field_size_classification"].value_counts(dropna=False).to_dict()
        if "field_size_classification" in merged_df.columns
        else {}
    )
    print(
        json.dumps(
            {
                "slate_id": slate_id,
                "matched_rows": matched_count,
                "classification_counts": classification_counts,
                "output": str(DK_ENTRIES_CLASSIFIED_CSV),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()


