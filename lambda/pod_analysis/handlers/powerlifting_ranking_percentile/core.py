"""
Powerlifting Stats Tool — powerlifting_ranking_percentile (Lambda copy)
------------------------------------------------------------------------
Copied verbatim (trimmed) from tools/health/powerlifting_stats.py.
Only the intra-package config import is adjusted to the layer copy.
"""

import os
import glob
import logging
import threading
from datetime import date
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
            low_memory=True
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
    import threading as _t
    _alive = any(th.name == "pl-cache-warm" and th.is_alive() for th in _t.enumerate())
    if not _alive:
        warm_cache()
    raise DatasetNotReadyError(
        "The dataset is still loading in the background. Try again in a moment."
    )

_IPF_CLASSES: Dict[str, list] = {
    "M": [59.0, 66.0, 74.0, 83.0, 93.0, 105.0, 120.0, float("inf")],
    "F": [47.0, 52.0, 57.0, 63.0, 69.0, 76.0, 84.0, float("inf")],
}

_wc_slice_cache: Dict[str, pd.DataFrame] = {}
_wc_slice_lock = threading.Lock()

def _user_class_bounds(bodyweight_kg: float, sex_code: str) -> tuple:
    """Return (lower_exclusive_kg, upper_inclusive_kg) for the user's IPF weight
    class, plus ±1 adjacent class to capture WRPF/USAPL/etc. variants that sit
    fractionally below the IPF limit (e.g. 82.5 for the 83kg slot).

    We include the class below and above so a 78kg lifter in the 83kg class
    is compared against the 74kg AND 83kg AND 93kg pools — i.e. anyone whose
    bodyweight is >66kg and <=93kg.  That gives 3 neighbouring classes, which
    is what the plan requested.
    """
    classes = _IPF_CLASSES.get(sex_code)
    if not classes or bodyweight_kg <= 0:
        return (0.0, float("inf"))

    idx = next((i for i, c in enumerate(classes) if bodyweight_kg <= c), len(classes) - 1)

    start = max(0, idx - 1)
    end   = min(len(classes) - 1, idx + 1)

    lower = classes[start - 1] if start > 0 else 0.0
    upper = classes[end]
    return (lower, upper)

def _get_or_build_wc_slice(df: pd.DataFrame, bodyweight_kg: float, sex_code: str) -> pd.DataFrame:
    """Lazily build and cache the ±1-class-neighbourhood slice.

    Uses BodyweightKg directly — federation-agnostic.  A WRPF 82.5kg lifter
    fits inside the 83kg band (>74 and <=83) just as an IPF 83kg lifter does.
    """
    lower, upper = _user_class_bounds(bodyweight_kg, sex_code)
    cache_key = f"{sex_code}_{lower}_{upper}"
    with _wc_slice_lock:
        if cache_key not in _wc_slice_cache:
            mask = (df["BodyweightKg"] > lower) & (df["BodyweightKg"] <= upper)
            _wc_slice_cache[cache_key] = df[mask].copy()
        return _wc_slice_cache[cache_key]

def _three_year_deduplicated(df: pd.DataFrame) -> pd.DataFrame:
    """Keep last 3 calendar years; deduplicate by Name keeping best TotalKg."""
    current_year = date.today().year
    min_year = current_year - 2
    if "Year" not in df.columns:
        return df
    recent = df[(df["Year"] >= min_year) & (df["Year"] <= current_year)].copy()
    if "Name" not in recent.columns or recent.empty:
        return recent
    recent = recent.sort_values("TotalKg", ascending=False, na_position="last")
    return recent.drop_duplicates(subset=["Name"], keep="first")

def _percentile_for(value: Optional[float], series: "pd.Series") -> Optional[int]:
    """Top-X percentile (0-100) of value within series; None if <10 entries."""
    if value is None or value <= 0:
        return None
    arr = series.dropna().values
    if len(arr) < 10:
        return None
    return int(round(float(np.sum(arr < value) / len(arr) * 100)))

def _top10_mean_for(series: "pd.Series") -> Optional[float]:
    """Mean of the top 25% of values in series; None if <10 entries."""
    arr = series.dropna().values
    if len(arr) < 10:
        return None
    threshold = np.percentile(arr, 75)
    top = arr[arr >= threshold]
    if len(top) == 0:
        return None
    return round(float(top.mean()), 1)

def compute_ranking_percentiles(
    df: pd.DataFrame,
    squat_kg: Optional[float] = None,
    bench_kg: Optional[float] = None,
    deadlift_kg: Optional[float] = None,
    bodyweight_kg: Optional[float] = None,
    sex_code: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    age_class: Optional[str] = None,
    equipment: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute national/regional/global percentile cards for the dashboard.

    Pipeline:
    1. Narrow df to 3 nearest IPF weight classes (by bodyweight_kg + sex_code)
    2. Apply sex / age_class / equipment filters
    3. Last 3 calendar years, deduplicate by Name (keep best TotalKg)
    4. Compute percentiles for Squat/Bench/Deadlift/Total across 3 geo scopes

    Returns::

        {
            "global":   {"squat": 72, "bench": 65, "deadlift": 80, "total": 74},
            "national": {"squat": 68, ...},   # None when country not given
            "regional": {"squat": 55, ...},   # None when region not given
            "meta":     {"global_n": 3200, "national_n": 410, "regional_n": 80},
        }

    Any lift value is None when <10 comparison lifters or lift not provided.
    """
    total_kg: Optional[float] = None
    if squat_kg and bench_kg and deadlift_kg:
        total_kg = squat_kg + bench_kg + deadlift_kg

    base_df = df
    if bodyweight_kg and bodyweight_kg > 0 and sex_code in ("M", "F"):
        base_df = _get_or_build_wc_slice(df, bodyweight_kg, sex_code)

    mask = pd.Series(True, index=base_df.index)
    if "Event" in base_df.columns:
        mask &= base_df["Event"].astype(str).str.strip() == "SBD"
    if sex_code and "Sex" in base_df.columns:
        mask &= base_df["Sex"].astype(str).str.strip() == sex_code
    if age_class and "AgeClass" in base_df.columns:
        mask &= base_df["AgeClass"].astype(str).str.strip() == age_class
    if equipment and "Equipment" in base_df.columns:
        mask &= base_df["Equipment"].astype(str).str.strip() == equipment
    filtered_base = base_df[mask].copy()

    global_df = _three_year_deduplicated(filtered_base)

    national_df: Optional[pd.DataFrame] = None
    regional_df: Optional[pd.DataFrame] = None
    if country and "MeetCountry" in global_df.columns:
        nat_mask = global_df["MeetCountry"].astype(str).str.strip() == country
        national_df = global_df[nat_mask].copy()
        if region and "State" in national_df.columns:
            reg_mask = national_df["State"].astype(str).str.strip() == region
            regional_df = national_df[reg_mask].copy()

    def _card(scope_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        if scope_df is None or scope_df.empty:
            return {
                "squat": None, "bench": None, "deadlift": None, "total": None,
                "top10_mean_squat": None, "top10_mean_bench": None,
                "top10_mean_deadlift": None, "top10_mean_total": None,
            }
        empty = pd.Series(dtype="float32")
        s_ser  = scope_df["Best3SquatKg"]    if "Best3SquatKg"    in scope_df.columns else empty
        b_ser  = scope_df["Best3BenchKg"]    if "Best3BenchKg"    in scope_df.columns else empty
        dl_ser = scope_df["Best3DeadliftKg"] if "Best3DeadliftKg" in scope_df.columns else empty
        t_ser  = scope_df["TotalKg"]         if "TotalKg"         in scope_df.columns else empty
        return {
            "squat":    _percentile_for(squat_kg,    s_ser),
            "bench":    _percentile_for(bench_kg,    b_ser),
            "deadlift": _percentile_for(deadlift_kg, dl_ser),
            "total":    _percentile_for(total_kg,    t_ser),
            "top10_mean_squat":    _top10_mean_for(s_ser),
            "top10_mean_bench":    _top10_mean_for(b_ser),
            "top10_mean_deadlift": _top10_mean_for(dl_ser),
            "top10_mean_total":    _top10_mean_for(t_ser),
        }

    weight_class_label: Optional[str] = None
    if bodyweight_kg and bodyweight_kg > 0 and sex_code in ("M", "F"):
        classes = _IPF_CLASSES[sex_code]
        for cls in classes:
            if bodyweight_kg <= cls:
                weight_class_label = f"{int(cls)}kg" if cls != float("inf") else f"{int(classes[-2])}kg+"
                break

    return {
        "global":   _card(global_df),
        "national": _card(national_df),
        "regional": _card(regional_df),
        "weight_class_label": weight_class_label,
        "meta": {
            "global_n":   len(global_df),
            "national_n": len(national_df) if national_df is not None else None,
            "regional_n": len(regional_df) if regional_df is not None else None,
        },
    }

warm_cache()
