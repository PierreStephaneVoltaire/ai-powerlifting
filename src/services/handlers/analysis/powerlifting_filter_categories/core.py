"""
Powerlifting Stats Tool — powerlifting_filter_categories 
----------------------------------------------------------------------
Copied verbatim (trimmed) from tools/health/powerlifting_stats.py.
Only the intra-package config import is adjusted to the layer copy.
"""

import os
import logging
import pandas as pd
from typing import Dict, Any, List, Optional

from services.lib.opl_dataset import DatasetNotReadyError, warm_cache
from services.lib import opl_dataset


logger = logging.getLogger(__name__)


def load_data() -> pd.DataFrame:
    return opl_dataset.load_data(block=False)


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
