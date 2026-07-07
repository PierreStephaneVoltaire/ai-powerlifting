"""
Powerlifting Stats Tool — analyze_powerlifting_stats (Lambda copy)
------------------------------------------------------------------
Copied verbatim (trimmed) from tools/health/powerlifting_stats.py.
Only the intra-package config import is adjusted to the layer copy.
"""

import os
import glob
import logging
import threading
import pandas as pd
import numpy as np
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
        for page in paginator.paginate(Bucket=bucket, Prefix="openpowerlifting-"):
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

_DOTS_COEFFS: Dict[str, tuple] = {
    "M": (-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093),
    "F": (-57.96288,  13.6175032, -0.1126655495, 0.0005158568, -0.0000010706),
}

def compute_dots(total_kg: float, bw_kg: float, sex_code: str) -> Optional[float]:
    coeffs = _DOTS_COEFFS.get(sex_code)
    if not coeffs or bw_kg <= 0 or total_kg <= 0:
        return None
    a, b, c, d, e = coeffs
    denom = a + b*bw_kg + c*bw_kg**2 + d*bw_kg**3 + e*bw_kg**4
    if denom == 0:
        return None
    return round(500 / denom * total_kg, 2)

def filter_dataset(
    df: pd.DataFrame,
    federation: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    equipment: Optional[str] = None,
    sex: Optional[str] = None,
    age_class: Optional[str] = None,
    year: Optional[int] = None,
    event_type: Optional[str] = None,
    min_dots: Optional[float] = None,
) -> pd.DataFrame:
    """Filters the dataset based on any combination of parameters."""
    mask = pd.Series(True, index=df.index)

    if federation:
        mask &= (df["Federation"].astype(str).str.strip() == federation)
    if country:
        mask &= (df["MeetCountry"].astype(str).str.strip() == country)
    if region:
        mask &= (df["State"].astype(str).str.strip() == region)
    if equipment:
        mask &= (df["Equipment"].astype(str).str.strip() == equipment)
    if sex:
        mask &= (df["Sex"].astype(str).str.strip() == sex)
    if age_class:
        mask &= (df["AgeClass"].astype(str).str.strip() == age_class)
    if year:
        mask &= (df["Year"] == year)
    if event_type:
        mask &= (df["Event"].astype(str).str.strip() == event_type)
    if min_dots is not None and "Dots" in df.columns:
        mask &= (df["Dots"] >= min_dots)

    return df[mask].copy()

def rank_value(value: float, series: pd.Series) -> dict:
    """Compute statistics for a specific value against a series."""
    if pd.isna(value) or value <= 0:
        return {}

    arr = series.dropna().values
    n = len(arr)
    if n == 0:
        return {"n": 0}

    beat = int(np.sum(arr < value))
    tied = int(np.sum(arr == value))

    return {
        "n": n,
        "rank": n - beat,
        "beat": beat,
        "tied": tied,
        "percentile": int(round(float(beat / n * 100))),
        "pct_of_max": round(value / arr.max() * 100, 2) if arr.max() > 0 else 0,
        "pct_of_mean": round(value / arr.mean() * 100, 2) if arr.mean() > 0 else 0,
        "median": round(float(np.median(arr)), 2),
        "mean": round(float(arr.mean()), 2),
        "max": round(float(arr.max()), 2),
    }

def analyze_stats(
    filtered_df: pd.DataFrame,
    squat_kg: Optional[float] = None,
    bench_kg: Optional[float] = None,
    deadlift_kg: Optional[float] = None,
    bodyweight_kg: Optional[float] = None,
    sex_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns statistical analysis comparing the user's lifts to the filtered dataset.

    Total and DOTS are derived from inputs — callers should not supply them directly.
    """
    total_kg: Optional[float] = None
    if squat_kg and bench_kg and deadlift_kg:
        total_kg = squat_kg + bench_kg + deadlift_kg

    dots_val: Optional[float] = None
    if total_kg and bodyweight_kg and sex_code:
        dots_val = compute_dots(total_kg, bodyweight_kg, sex_code)

    results: Dict[str, Any] = {
        "dataset_size": len(filtered_df),
        "computed": {"total_kg": total_kg, "dots": dots_val},
        "analysis": {},
    }

    if len(filtered_df) == 0:
        return results

    metrics = [
        ("Squat",    squat_kg,    "Best3SquatKg"),
        ("Bench",    bench_kg,    "Best3BenchKg"),
        ("Deadlift", deadlift_kg, "Best3DeadliftKg"),
        ("Total",    total_kg,    "TotalKg"),
        ("Dots",     dots_val,    "Dots"),
    ]

    for label, user_val, col in metrics:
        if user_val is not None and user_val > 0 and col in filtered_df.columns:
            results["analysis"][label] = rank_value(user_val, filtered_df[col])

    return results

warm_cache()
