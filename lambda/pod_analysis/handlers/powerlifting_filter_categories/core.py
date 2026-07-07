"""
Powerlifting Stats Tool — powerlifting_filter_categories (Lambda copy)
----------------------------------------------------------------------
Copied verbatim (trimmed) from tools/health/powerlifting_stats.py.
Only the intra-package config import is adjusted to the layer copy.
"""

import os
import glob
import logging
import threading
import pandas as pd
from typing import Dict, Any, List, Optional

from .config import SANDBOX_PATH

logger = logging.getLogger(__name__)

class DatasetNotReadyError(Exception):
    """Raised when the DataFrame cache has not finished loading yet."""

_df_cache: Optional[pd.DataFrame] = None
_df_lock = threading.Lock()
_df_ready = threading.Event()
_df_error: Optional[str] = None


def _ensure_dataset_downloaded() -> None:
    """Download OpenPowerlifting CSVs from S3 to SANDBOX_PATH if not present.

    Reads POWERLIFTING_S3_BUCKET (injected by the Fission function env when
    resources.yaml sets s3_read: true). Skips the download if the local cache
    already has any matching file, so cold start pays the cost exactly once
    per pod lifetime.
    """
    pattern = os.path.join(SANDBOX_PATH, "openpowerlifting-*.csv")
    if glob.glob(pattern):
        return
    bucket = os.environ.get("POWERLIFTING_S3_BUCKET", "")
    if not bucket:
        return
    try:
        import boto3
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ca-central-1"))
        os.makedirs(SANDBOX_PATH, exist_ok=True)
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="datasets/openpowerlifting-"):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                if not key.endswith(".csv"):
                    continue
                dest = os.path.join(SANDBOX_PATH, os.path.basename(key))
                if os.path.isfile(dest) and os.path.getsize(dest) == obj.get("Size", 0):
                    continue
                logger.info(f"[Powerlifting] Downloading s3://{bucket}/{key} -> {dest}")
                s3.download_file(bucket, key, dest)
    except Exception as e:
        logger.warning(f"[Powerlifting] S3 dataset download skipped: {e}")


def _parse_csvs() -> pd.DataFrame:
    """Read and parse all matching CSVs from sandbox. Called only from background thread."""
    _ensure_dataset_downloaded()
    pattern = os.path.join(SANDBOX_PATH, "openpowerlifting-*.csv")
    csv_files = glob.glob(pattern)

    if not csv_files:
        raise FileNotFoundError(f"No powerlifting datasets found in sandbox matching: {pattern}")
    csv_files = glob.glob(pattern)

    if not csv_files:
        raise FileNotFoundError(f"No powerlifting datasets found in sandbox matching: {pattern}")

    logger.info(f"[Powerlifting] Found {len(csv_files)} dataset(s): {csv_files}")

    usecols = [
        "Name", "Federation", "MeetCountry", "State", "Equipment", "Sex", "AgeClass", "Event",
        "Best3SquatKg", "Best3BenchKg", "Best3DeadliftKg", "TotalKg",
        "Dots", "Age", "BodyweightKg", "Date"
    ]
    dtypes = {
        "Name": "str",
        "Federation": "category",
        "MeetCountry": "category",
        "State": "category",
        "Equipment": "category",
        "Sex": "category",
        "AgeClass": "category",
        "Event": "category",
        "Best3SquatKg": "float32",
        "Best3BenchKg": "float32",
        "Best3DeadliftKg": "float32",
        "TotalKg": "float32",
        "Dots": "float32",
        "Age": "float32",
        "BodyweightKg": "float32",
    }

    dfs = []
    for csv_path in csv_files:
        logger.info(f"[Powerlifting] Parsing {csv_path}...")
        df = pd.read_csv(
            csv_path,
            usecols=lambda c: c in usecols,
            dtype={k: v for k, v in dtypes.items() if k in usecols},
            low_memory=False
        )
        dfs.append(df)

    if not dfs:
        raise ValueError("No data could be loaded from the CSV files.")

    combined_df = pd.concat(dfs, ignore_index=True)

    if "Date" in combined_df.columns and "Year" not in combined_df.columns:
        combined_df["Date"] = pd.to_datetime(combined_df["Date"], errors="coerce")
        combined_df["Year"] = combined_df["Date"].dt.year.astype("float32")

    return combined_df

def _background_load():
    """Background thread: parse CSVs and populate the cache."""
    global _df_cache, _df_error
    with _df_lock:
        if _df_ready.is_set():
            return
    try:
        logger.info("[Powerlifting] Starting background DataFrame load...")
        df = _parse_csvs()
        with _df_lock:
            _df_cache = df
            _df_ready.set()
        logger.info(f"[Powerlifting] DataFrame ready — {len(df):,} rows loaded into cache.")
    except FileNotFoundError as e:
        with _df_lock:
            _df_error = str(e)
        logger.warning(f"[Powerlifting] Dataset not found during background load: {e}")
    except Exception as e:
        with _df_lock:
            _df_error = str(e)
        logger.error(f"[Powerlifting] Background load failed: {e}", exc_info=True)

def warm_cache():
    """Trigger background DataFrame load. Idempotent — safe to call multiple times."""
    if _df_ready.is_set():
        return
    thread = threading.Thread(target=_background_load, daemon=True, name="pl-cache-warm")
    thread.start()

def load_data() -> pd.DataFrame:
    """Return the cached DataFrame. Raises if not ready yet or permanently missing."""
    if _df_ready.is_set() and _df_cache is not None:
        return _df_cache
    if _df_error and "No powerlifting datasets" in _df_error:
        raise FileNotFoundError(_df_error)
    raise DatasetNotReadyError(
        "The dataset is still loading in the background. Try again in a moment."
    )

def _group_unique(df: pd.DataFrame, group_col: str, value_col: str) -> Dict[str, List[str]]:
    if group_col not in df.columns or value_col not in df.columns:
        return {}
    sub = df[[group_col, value_col]].dropna()
    sub = sub[
        (sub[group_col].astype(str).str.strip() != "") &
        (sub[value_col].astype(str).str.strip() != "")
    ]
    return {
        str(k): sorted({str(v) for v in g[value_col].unique()})
        for k, g in sub.groupby(group_col, observed=True)
    }

def get_filter_categories(df: pd.DataFrame) -> Dict[str, Any]:
    """Retrieves unique categories and groupby maps to populate UI dropdowns."""
    options: Dict[str, Any] = {}

    categorical_cols = {
        "federations": "Federation",
        "countries": "MeetCountry",
        "regions": "State",
        "equipment": "Equipment",
        "sex": "Sex",
        "age_classes": "AgeClass",
        "event_types": "Event",
    }

    for key, col in categorical_cols.items():
        if col in df.columns:
            unique_vals = [x for x in df[col].unique() if pd.notna(x) and str(x).strip() != ""]
            options[key] = sorted(unique_vals)

    if "Year" in df.columns:
        options["years"] = sorted([int(x) for x in df["Year"].unique() if pd.notna(x)], reverse=True)

    options["country_federations"] = _group_unique(df, "MeetCountry", "Federation")
    options["country_regions"]     = _group_unique(df, "MeetCountry", "State")
    options["region_federations"]  = _group_unique(df, "State", "Federation")

    return options

warm_cache()
