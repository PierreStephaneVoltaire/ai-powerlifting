"""
Powerlifting Stats Tool — analyze_powerlifting_stats 
------------------------------------------------------------------
Copied verbatim (trimmed) from tools/health/powerlifting_stats.py.
Only the intra-package config import is adjusted to the layer copy.
"""

import os
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional

from services.lib.opl_dataset import DatasetNotReadyError, warm_cache
from services.lib import opl_dataset


logger = logging.getLogger(__name__)


def load_data() -> pd.DataFrame:
    return opl_dataset.load_data(block=False)


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
