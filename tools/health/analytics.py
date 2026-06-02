"""Deterministic training analytics algorithms.

Pure functions — no DynamoDB access, no LLM calls.
All math is stdlib only (math, statistics). JSON-serializable return values.

Canonical DOTS coefficients ported from:
  utils/powerlifting-app/frontend/src/utils/dots.ts
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Literal, Optional

from scipy.stats import kendalltau, theilslopes

DOTS_COEFFICIENTS: dict[str, dict[str, float]] = {
    "male": {
        "a": -307.75076,
        "b": 24.0900756,
        "c": -0.1918759221,
        "d": 0.0007391293,
        "e": -0.000001093,
    },
    "female": {
        "a": -57.96288,
        "b": 13.6175032,
        "c": -0.1126655495,
        "d": 0.0005158568,
        "e": -0.0000010706,
    },
}

_RPE_TABLE_PRIMARY: dict[tuple[int, int], float] = {
    (1, 10): 1.000, (2, 10): 0.960, (3, 10): 0.930, (4, 10): 0.900,
    (5, 10): 0.880, (6, 10): 0.860, (7, 10): 0.840, (8, 10): 0.820,
    (9, 10): 0.800, (10, 10): 0.780,
    (1, 9): 1.000, (2, 9): 0.940, (3, 9): 0.900, (4, 9): 0.870,
    (5, 9): 0.845, (6, 9): 0.825, (7, 9): 0.805, (8, 9): 0.785,
    (9, 9): 0.765, (10, 9): 0.745,
    (1, 8): 1.000, (2, 8): 0.920, (3, 8): 0.875, (4, 8): 0.845,
    (5, 8): 0.815, (6, 8): 0.795, (7, 8): 0.775, (8, 8): 0.755,
    (9, 8): 0.735, (10, 8): 0.715,
    (1, 7): 1.000, (2, 7): 0.900, (3, 7): 0.850, (4, 7): 0.820,
    (5, 7): 0.795, (6, 7): 0.775, (7, 7): 0.755, (8, 7): 0.735,
    (9, 7): 0.715, (10, 7): 0.695,
    (1, 6): 1.000, (2, 6): 0.880, (3, 6): 0.830, (4, 6): 0.800,
    (5, 6): 0.775, (6, 6): 0.755, (7, 6): 0.735, (8, 6): 0.715,
    (9, 6): 0.695, (10, 6): 0.675,
}

INSUFFICIENT_DATA = {"status": "insufficient_data"}

_DEFAULT_FATIGUE_PROFILE = {
    "axial": 0.3,
    "neural": 0.3,
    "peripheral": 0.5,
    "systemic": 0.3,
}

_FATIGUE_AXIAL_EXPONENT = 1.30
_FATIGUE_PERIPHERAL_EXPONENT = 1.15
_FATIGUE_SYSTEMIC_BETA = 0.30
_FATIGUE_NEURAL_FLOOR = 0.60
_FATIGUE_NEURAL_CEILING = 0.995
_FATIGUE_NEURAL_LOAD_SCALE = 100.0
_FATIGUE_RESERVOIR_HALF_LIFE_DAYS = {
    "systemic": 2.0,
    "peripheral": 4.0,
    "axial": 5.0,
    "neural": 6.0,
}
_FATIGUE_RESERVOIR_BASELINE_LOOKBACK_DAYS = 56
_FATIGUE_RESERVOIR_BASELINE_GAP_DAYS = 14

_INOL_EPSILON = 0.02
_INOL_INTENSITY_CEILING = 0.995
_DEFAULT_INOL_THRESHOLDS = {
    "squat": {"low": 1.6, "high": 3.5},
    "bench": {"low": 2.0, "high": 5.0},
    "deadlift": {"low": 1.0, "high": 2.5},
}

_ACWR_ACUTE_LAMBDA = 2 / (7 + 1)
_ACWR_CHRONIC_LAMBDA = 2 / (28 + 1)
_ACWR_MIN_DAYS = 25
_ACWR_ZONE_LABELS = {
    "detraining_trend": "Detraining trend",
    "steady_load": "Steady load",
    "rapid_increase": "Rapid increase",
    "load_spike": "Load spike",
}

_DIMENSION_WEIGHTS = {
    "axial": 0.30,
    "neural": 0.30,
    "peripheral": 0.25,
    "systemic": 0.15,
}
_BANISTER_CTL_LAMBDA = 2 / 43
_BANISTER_ATL_LAMBDA = 2 / 8
_BANISTER_SEED_DAYS = 14
_MONOTONY_EPSILON = 1e-6
_MONOTONY_RELATIVE_SD_FLOOR = 0.10
_MONOTONY_ABSOLUTE_SD_FLOOR = 1.0
_MONOTONY_DISPLAY_CAP = 7.0
_DECOUPLING_WINDOW_WEEKS = 3
_TAPER_WINDOW_WEEKS = 3
_TAPER_PRE_TAPER_WEEKS = 4
_TAPER_INTENSITY_RATIO_FLOOR = 0.95
_TAPER_FI_SLOPE_SCALE = 0.10
_TAPER_FI_DIFF_SCALE = 0.20
_PROJECTION_MIN_MULTIPLIER = 0.92
_PROJECTION_MAX_MULTIPLIER = 1.05
_PROJECTION_MIN_CALIBRATED_MEETS = 2
_VOLUME_LANDMARK_MIN_WEEKS = 12

_SPECIFICITY_BANDS: list[dict[str, Any]] = [
    {
        "min_weeks": 16,
        "max_weeks": None,
        "narrow": {"min": 0.30, "max": 0.50},
        "broad": {"min": 0.60, "max": 0.75},
    },
    {
        "min_weeks": 12,
        "max_weeks": 16,
        "narrow": {"min": 0.40, "max": 0.55},
        "broad": {"min": 0.65, "max": 0.80},
    },
    {
        "min_weeks": 8,
        "max_weeks": 12,
        "narrow": {"min": 0.50, "max": 0.65},
        "broad": {"min": 0.75, "max": 0.85},
    },
    {
        "min_weeks": 4,
        "max_weeks": 8,
        "narrow": {"min": 0.60, "max": 0.75},
        "broad": {"min": 0.80, "max": 0.90},
    },
    {
        "min_weeks": 0,
        "max_weeks": 4,
        "narrow": {"min": 0.70, "max": 0.85},
        "broad": {"min": 0.85, "max": 0.95},
    },
]

_CONSERVATIVE_REP_PCT: dict[int, float] = {
    1: 1.000,
    2: 0.955,
    3: 0.925,
    4: 0.898,
    5: 0.875,
}

_PRIMARY_LIFT_NAMES: frozenset[str] = frozenset({"squat", "deadlift"})

def _num(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (float, int)):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0

def _count_failed_sets(ex: dict) -> int:
    statuses = ex.get("set_statuses")
    if statuses and isinstance(statuses, list):
        return sum(1 for status in statuses if status == "failed")
    failed_arr = ex.get("failed_sets")
    if failed_arr and isinstance(failed_arr, list):
        return sum(1 for f in failed_arr if f)
    if ex.get("failed", False):
        return int(_num(ex.get("sets", 0)))
    return 0

def _executed_sets(ex: dict) -> float:
    statuses = ex.get("set_statuses")
    if statuses and isinstance(statuses, list):
        return float(sum(1 for status in statuses if status in {"completed", "failed"}))
    return _num(ex.get("sets", 0))

def _executed_volume(ex: dict) -> float:
    return _executed_sets(ex) * _num(ex.get("reps", 0)) * _num(ex.get("kg", 0))

def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return median(abs(v - center) for v in values)

def _fit_quality(xs: list[float], ys: list[float], slope: float, intercept: float) -> tuple[float, float]:
    if len(xs) < 2:
        return 0.0, 0.0
    tau = kendalltau(xs, ys, nan_policy="omit").statistic
    if tau is None or math.isnan(float(tau)):
        tau = 0.0
    predicted = [intercept + slope * x for x in xs]
    residuals = [y - p for y, p in zip(ys, predicted)]
    series_mad = _mad(ys)
    residual_mad = _mad(residuals)
    if series_mad <= 1e-12:
        quality = 1.0 if residual_mad <= 1e-12 else 0.0
    else:
        quality = _clamp(1.0 - (residual_mad / series_mad), 0.0, 1.0)
    return round(float(tau), 3), round(float(quality), 3)

def _estimate_e1rm_from_set(weight_kg: float, reps: int, rpe: Any = None) -> float | None:
    """Estimate 1RM from a single set using the same tables as the rest of the module."""
    if rpe is not None:
        try:
            rpe_int = int(rpe)
        except (ValueError, TypeError):
            rpe_int = None
        if rpe_int is not None and 1 <= reps <= 6 and 6 <= rpe_int <= 10:
            pct = _RPE_TABLE_PRIMARY.get((reps, rpe_int))
            if pct is not None:
                return weight_kg / pct
    elif 1 <= reps <= 5:
        pct = _CONSERVATIVE_REP_PCT.get(reps)
        if pct is not None:
            return weight_kg / pct
    return None

def _ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0.0
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 0.0, 0.0, 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    mean_y = sum_y / n
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r_squared = 1.0 - (ss_res / ss_tot) if abs(ss_tot) > 1e-12 else 0.0
    return slope, intercept, r_squared

def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x < 1e-12 or den_y < 1e-12:
        return 0.0
    return num / (den_x * den_y)

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

def _session_week_num(session: dict, program_start: str = "") -> Optional[int]:
    """Return the integer week number for a session.

    Uses the session's week_number field if available (preferred — always an integer).
    Falls back to computing from program_start date.
    """
    wn = session.get("week_number")
    if wn is not None:
        try:
            return int(wn)
        except (ValueError, TypeError):
            pass
    if program_start:
        d = _parse_date(session.get("date", ""))
        start = _parse_date(program_start)
        if d is not None and start is not None:
            return max(1, (d - start).days // 7 + 1)
    return None

def _parse_week_bound(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        week = int(value)
    except (ValueError, TypeError):
        return None
    return week if week > 0 else None

def _is_completed_session(session: dict) -> bool:
    return bool(session.get("completed") or session.get("status") in ("logged", "completed"))

def _resolve_week_window(
    sessions: list[dict],
    current_week: int,
    weeks: int,
    program_start: str = "",
    week_start: Any = None,
    week_end: Any = None,
) -> tuple[int, int]:
    """Resolve an inclusive training-week window using session.week_number."""
    start = _parse_week_bound(week_start)
    end = _parse_week_bound(week_end)
    if start is None and end is None:
        end = current_week
        start = max(1, end - max(1, int(weeks or 1)) + 1)
    elif start is None:
        start = max(1, end - max(1, int(weeks or 1)) + 1)
    elif end is None:
        end = start + max(1, int(weeks or 1)) - 1

    if start > end:
        start, end = end, start

    available = sorted(
        {
            wk
            for s in sessions
            if (wk := _session_week_num(s, program_start)) is not None
        }
    )
    if available:
        start = max(start, available[0])
        end = min(end, available[-1])
        if start > end:
            end = start
    return start, end

def _sessions_in_week_window(
    sessions: list[dict],
    program_start: str,
    week_start: int,
    week_end: int,
) -> list[dict]:
    return [
        s
        for s in sessions
        if (wk := _session_week_num(s, program_start)) is not None
        and week_start <= wk <= week_end
    ]

def _session_date_bounds(sessions: list[dict]) -> tuple[Optional[date], Optional[date]]:
    dates = sorted(d for s in sessions if (d := _parse_date(s.get("date", ""))) is not None)
    if not dates:
        return None, None
    return dates[0], dates[-1]

def _week_index(session: dict, program_start: str) -> Optional[float]:
    """Float week offset — kept for legacy callers; use _session_week_num for grouping."""
    d = _parse_date(session.get("date", ""))
    start = _parse_date(program_start)
    if d is None or start is None:
        return None
    return (d - start).days / 7.0

def _get_exercise_sessions(sessions: list[dict], exercise_name: str) -> list[dict]:
    name_lower = exercise_name.lower()
    out = []
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        for ex in s.get("exercises", []):
            if ex.get("name", "").lower() == name_lower:
                out.append(s)
                break
    return out

def _compute_weekly_volume_load(sessions: list[dict], program_start: str) -> dict[int, float]:
    weekly: dict[int, float] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        week_load = 0.0
        for ex in s.get("exercises", []):
            week_load += _executed_volume(ex)
        weekly[wk] = weekly.get(wk, 0.0) + week_load
    return weekly

def _best_primary_e1rm_for_sessions(w_sessions: list[dict]) -> Optional[float]:
    best: Optional[float] = None
    for s in w_sessions:
        session_rpe = s.get("session_rpe")
        for ex in s.get("exercises", []):
            if ex.get("name", "").lower().strip() not in _PRIMARY_LIFT_NAMES:
                continue
            if _count_failed_sets(ex) > 0 or _executed_sets(ex) <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or reps <= 0:
                continue
            rpe = session_rpe
            e1rm = None
            if rpe is not None and 1 <= reps <= 6 and 6 <= int(rpe) <= 10:
                pct = _RPE_TABLE_PRIMARY.get((reps, int(rpe)))
                if pct:
                    e1rm = kg / pct
            elif rpe is None and 1 <= reps <= 5:
                pct = _CONSERVATIVE_REP_PCT.get(reps)
                if pct:
                    e1rm = kg / pct
            if e1rm is not None and (best is None or e1rm > best):
                best = e1rm
    return best

def _detect_deloads(
    sessions: list[dict],
    program_start: str,
    threshold: float = 0.65,
    threshold_no_main: float = 0.75,
    rolling_window: int = 4,
) -> list[dict]:
    """Detect deload and break weeks.

    A week is a DELOAD if:
      1. VL < threshold * median(prev rolling_window non-deload weeks)
         (threshold_no_main if no squat/deadlift present)
      2. Intensity condition (only when primary lifts present):
         - RPE path: all primary RPEs <= 6
         - e1RM path: best e1RM dropped >= 10% vs prev 2 non-deload weeks
         - Stagnation is NOT a deload
    A week is a BREAK if zero volume load.
    week_index == week_num (int) for backward compat.
    """
    if not program_start:
        program_start = _infer_program_start(sessions)

    week_sessions: dict[int, list[dict]] = {}
    last_wk = 1
    for s in sessions:
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        if wk > last_wk:
            last_wk = wk
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        week_sessions.setdefault(wk, []).append(s)

    all_wks = list(range(1, last_wk + 1))
    results = []
    prev_non_deload_vls: list[float] = []
    prev_non_deload_e1rms: list[float] = []

    for wk in all_wks:
        w_sessions = week_sessions.get(wk, [])

        vl = sum(_executed_volume(ex) for s in w_sessions for ex in s.get("exercises", []))
        is_break = vl == 0.0

        has_main_lift = any(
            ex.get("name", "").lower().strip() in _PRIMARY_LIFT_NAMES
            and _executed_sets(ex) > 0
            for s in w_sessions for ex in s.get("exercises", [])
        )

        is_deload = False
        if not is_break and len(prev_non_deload_vls) >= 1:
            med = median(prev_non_deload_vls[-rolling_window:])
            thr = threshold if has_main_lift else threshold_no_main
            volume_condition = med > 0 and vl < thr * med

            if volume_condition:
                if not has_main_lift:
                    is_deload = True
                else:
                    primary_rpes: list[float] = []
                    for s in w_sessions:
                        if not any(
                            ex.get("name", "").lower().strip() in _PRIMARY_LIFT_NAMES
                            for ex in s.get("exercises", [])
                        ):
                            continue
                        rpe = s.get("session_rpe")
                        if rpe is not None:
                            primary_rpes.append(_num(rpe))
                        else:
                            for ex in s.get("exercises", []):
                                if ex.get("name", "").lower().strip() in _PRIMARY_LIFT_NAMES:
                                    ex_rpe = ex.get("rpe")
                                    if ex_rpe is not None:
                                        primary_rpes.append(_num(ex_rpe))

                    if primary_rpes:
                        intensity_condition = all(r <= 6 for r in primary_rpes)
                    else:
                        week_e1rm = _best_primary_e1rm_for_sessions(w_sessions)
                        if week_e1rm is not None and prev_non_deload_e1rms:
                            best_prev = max(prev_non_deload_e1rms[-2:])
                            intensity_condition = week_e1rm < best_prev * 0.90
                        else:
                            intensity_condition = False
                    is_deload = intensity_condition

        week_best_e1rm = _best_primary_e1rm_for_sessions(w_sessions)

        results.append({
            "week_num": wk,
            "week_index": wk,
            "is_deload": is_deload,
            "is_break": is_break,
            "volume_load": vl,
            "effective_index": -1,
        })

        if not is_deload and not is_break:
            prev_non_deload_vls.append(vl)
            if week_best_e1rm is not None:
                prev_non_deload_e1rms.append(week_best_e1rm)

    eff_idx = 0
    for r in results:
        if not r["is_deload"] and not r["is_break"]:
            r["effective_index"] = eff_idx
            eff_idx += 1

    return results

def _effective_training_data(
    sessions: list[dict],
    program_start: str,
) -> tuple[list[dict], dict[int, int]]:
    deload_info = _detect_deloads(sessions, program_start)
    excluded_weeks: set[int] = set()
    effective_map: dict[int, int] = {}
    for d in deload_info:
        if d["is_deload"] or d["is_break"]:
            excluded_weeks.add(d["week_num"])
        else:
            effective_map[d["week_num"]] = d["effective_index"]
    filtered = [s for s in sessions if _session_week_num(s, program_start) not in excluded_weeks]
    return filtered, effective_map

logger = logging.getLogger(__name__)

def _get_fatigue_profile(exercise_name: str, glossary: list[dict] | None = None) -> dict:
    if glossary:
        name_lower = exercise_name.lower().strip()
        for ex in glossary:
            if ex.get("name", "").lower().strip() == name_lower:
                profile = ex.get("fatigue_profile")
                if isinstance(profile, dict) and all(k in profile for k in ("axial", "neural", "peripheral", "systemic")):
                    return profile
    logger.warning(f"No fatigue profile for {exercise_name}")
    return dict(_DEFAULT_FATIGUE_PROFILE)

def _neural_scaling(I: float) -> float:
    if I <= _FATIGUE_NEURAL_FLOOR:
        return 0.0
    return ((I - _FATIGUE_NEURAL_FLOOR) / (_FATIGUE_NEURAL_CEILING - _FATIGUE_NEURAL_FLOOR)) ** 3

def _per_set_fatigue(weight: float, reps: int, profile: dict, I: float, rpe: float | None = None) -> dict:
    rpe_multiplier = 1.0
    if rpe is not None and rpe > 0:
        rpe_multiplier += 0.20 * _clamp((rpe - 7.0) / 3.0, 0.0, 1.0)
    return {
        "axial": profile["axial"] * (weight ** _FATIGUE_AXIAL_EXPONENT) * reps,
        "neural": profile["neural"] * reps * _neural_scaling(I) * math.sqrt(max(weight, 0.0) / _FATIGUE_NEURAL_LOAD_SCALE) * rpe_multiplier,
        "peripheral": profile["peripheral"] * (weight ** _FATIGUE_PERIPHERAL_EXPONENT) * reps * rpe_multiplier,
        "systemic": profile["systemic"] * weight * reps * (1 + _FATIGUE_SYSTEMIC_BETA * I) * rpe_multiplier,
    }

def _weekly_fatigue_by_dimension(
    sessions: list[dict],
    glossary: list[dict] | None,
    program_start: str,
    current_maxes: dict,
) -> dict[int, dict[str, float]]:
    """Keyed by integer week_number."""
    weekly: dict[int, dict[str, float]] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        week_dim = weekly.get(wk, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        for ex in s.get("exercises", []):
            name = ex.get("name", "").strip()
            kg = _num(ex.get("kg", 0))
            sets = int(_executed_sets(ex))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or sets <= 0 or reps <= 0:
                continue
            profile = _get_fatigue_profile(name, glossary)
            name_lower = name.lower()
            rpe = ex.get("rpe")
            if rpe is None:
                rpe = s.get("session_rpe")
            rpe_num = _num(rpe) if rpe is not None else None
            I = _resolve_intensity(name_lower, kg, reps, rpe_num, current_maxes, glossary)
            sf = _per_set_fatigue(kg, reps, profile, I, rpe_num)
            for dim in ("axial", "neural", "peripheral", "systemic"):
                week_dim[dim] += sf[dim] * sets
        weekly[wk] = week_dim
    return weekly

def _resolve_intensity(name_lower: str, weight: float, reps: int, rpe: float | None, current_maxes: dict, glossary: list[dict] | None) -> float:
    e1rm = None
    cat = "isolation"
    
    if name_lower == "squat": e1rm = current_maxes.get("squat")
    elif name_lower in ("bench press", "bench"): e1rm = current_maxes.get("bench")
    elif name_lower == "deadlift": e1rm = current_maxes.get("deadlift")
    
    if e1rm and _num(e1rm) > 0: return min(1.0, weight / _num(e1rm))
    
    if glossary:
        for g in glossary:
            if g.get("name", "").lower().strip() == name_lower:
                raw_e1rm = g.get("e1rm_estimate", g.get("e1rm"))
                if isinstance(raw_e1rm, dict):
                    e1rm = (
                        raw_e1rm.get("kg")
                        or raw_e1rm.get("e1rm_kg")
                        or raw_e1rm.get("estimate_kg")
                        or raw_e1rm.get("value_kg")
                    )
                else:
                    e1rm = raw_e1rm
                cat = g.get("category", "isolation")
                break
    
    if e1rm and _num(e1rm) > 0: return min(1.0, weight / _num(e1rm))
    
    if rpe is not None and rpe > 0:
        est = _estimate_e1rm_from_set(weight, reps, rpe)
        if est and est > 0: return min(1.0, weight / est)
        
    if weight > 0 and reps > 0:
        est = weight * (1 + reps / 30.0)
        epley_i = min(1.0, weight / est)
        if cat in ("squat", "bench", "deadlift", "main", "competition"):
            return _clamp(epley_i, 0.60, 0.95)
        if "variation" in cat:
            return _clamp(epley_i, 0.55, 0.90)
        if "machine" in cat or "compound" in cat:
            return _clamp(epley_i, 0.50, 0.85)
        return _clamp(epley_i, 0.45, 0.80)
        
    if cat in ("main", "competition"): return 0.75
    if "variation" in cat: return 0.70
    if "machine" in cat or "compound" in cat: return 0.65
    return 0.55

def _daily_fatigue_by_dimension(
    sessions: list[dict],
    glossary: list[dict] | None,
    program_start: str,
    current_maxes: dict,
) -> dict[date, dict[str, float]]:
    """Keyed by calendar date for EWMA ACWR calculations."""
    daily: dict[date, dict[str, float]] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        d = _parse_date(s.get("date", ""))
        if d is None:
            continue
        day_dim = daily.setdefault(d, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        for ex in s.get("exercises", []):
            name = ex.get("name", "").strip()
            kg = _num(ex.get("kg", 0))
            sets = int(_executed_sets(ex))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or sets <= 0 or reps <= 0:
                continue
            profile = _get_fatigue_profile(name, glossary)
            name_lower = name.lower()
            rpe = ex.get("rpe")
            if rpe is None:
                rpe = s.get("session_rpe")
            rpe_num = _num(rpe) if rpe is not None else None
            I = _resolve_intensity(name_lower, kg, reps, rpe_num, current_maxes, glossary)
            sf = _per_set_fatigue(kg, reps, profile, I, rpe_num)
            for dim in ("axial", "neural", "peripheral", "systemic"):
                day_dim[dim] += sf[dim] * sets
    return daily

def _fatigue_reservoir_series(
    sessions: list[dict],
    glossary: list[dict] | None,
    program_start: str,
    current_maxes: dict,
    ref_date: date,
) -> list[dict[str, Any]]:
    daily_dims = _daily_fatigue_by_dimension(
        sessions,
        glossary,
        program_start,
        current_maxes,
    )
    if not daily_dims:
        return []

    start_day = _parse_date(program_start) or min(daily_dims.keys())
    reservoirs = {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0}
    series: list[dict[str, Any]] = []

    day = start_day
    while day <= ref_date:
        dims = daily_dims.get(day, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        row: dict[str, Any] = {"date": day}
        for dim in ("axial", "neural", "peripheral", "systemic"):
            decay = math.exp(-math.log(2) / _FATIGUE_RESERVOIR_HALF_LIFE_DAYS[dim])
            reservoirs[dim] = reservoirs[dim] * decay + dims.get(dim, 0.0)
            row[dim] = reservoirs[dim]
        series.append(row)
        day += timedelta(days=1)

    return series

def _reservoir_stress_for_day(
    reservoir_series: list[dict[str, Any]],
    target_day: date,
) -> dict[str, Any]:
    by_date = {row["date"]: row for row in reservoir_series}
    current = by_date.get(target_day)
    if not current:
        return {
            "dimensions": {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0},
            "weighted": 0.0,
            "max_dimension": 0.0,
            "composite": 0.0,
            "confidence": "low",
            "context_days_used": 0,
        }

    baseline_start = target_day - timedelta(days=_FATIGUE_RESERVOIR_BASELINE_LOOKBACK_DAYS)
    baseline_end = target_day - timedelta(days=_FATIGUE_RESERVOIR_BASELINE_GAP_DAYS)
    baseline_rows = [
        row for row in reservoir_series
        if baseline_start <= row["date"] <= baseline_end
    ]

    if len(baseline_rows) >= 28:
        confidence = "high"
    elif len(baseline_rows) >= 14:
        confidence = "medium"
    else:
        confidence = "low"

    stresses: dict[str, float] = {}
    for dim in ("axial", "neural", "peripheral", "systemic"):
        vals = [row.get(dim, 0.0) for row in baseline_rows if row.get(dim, 0.0) > 0]
        if vals:
            baseline = median(vals)
            ratio = current.get(dim, 0.0) / baseline if baseline > 0 else 0.0
            stresses[dim] = _clamp((ratio - 1.0) / 0.75, 0.0, 1.0)
        else:
            stresses[dim] = 0.0

    weighted = sum(stresses[dim] * _DIMENSION_WEIGHTS[dim] for dim in _DIMENSION_WEIGHTS)
    max_dimension = max(stresses.values()) if stresses else 0.0
    composite = 0.60 * max_dimension + 0.40 * weighted

    return {
        "dimensions": {dim: round(stresses[dim], 3) for dim in stresses},
        "weighted": round(weighted, 3),
        "max_dimension": round(max_dimension, 3),
        "composite": round(composite, 3),
        "confidence": confidence,
        "context_days_used": len(baseline_rows),
    }

def _composite_load_from_dimensions(dimensions: dict[str, float]) -> float:
    return sum(dimensions.get(dim, 0.0) * weight for dim, weight in _DIMENSION_WEIGHTS.items())

def _banister_dimension_baselines(
    sessions: list[dict],
    glossary: list[dict] | None,
    program_start: str,
    current_maxes: dict,
) -> dict[str, float]:
    weekly_dims = _weekly_fatigue_by_dimension(sessions, glossary, program_start, current_maxes)
    deload_info = _detect_deloads(sessions, program_start)
    deload_weeks = {d["week_num"] for d in deload_info if d["is_deload"] or d["is_break"]}
    valid_weeks = [w for w in weekly_dims if w not in deload_weeks]
    baselines = {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}

    if len(valid_weeks) >= 3:
        for dim in baselines:
            vals = sorted(
                weekly_dims[w].get(dim, 0.0)
                for w in valid_weeks
                if weekly_dims[w].get(dim, 0.0) > 0
            )
            if vals:
                baselines[dim] = max(median(vals) / 7.0, 1.0)

    return baselines

def _normalized_banister_load(dims: dict[str, float], baselines: dict[str, float]) -> float:
    return 100.0 * (
        0.30 * dims.get("axial", 0.0) / max(baselines.get("axial", 1.0), 1.0)
        + 0.30 * dims.get("neural", 0.0) / max(baselines.get("neural", 1.0), 1.0)
        + 0.25 * dims.get("peripheral", 0.0) / max(baselines.get("peripheral", 1.0), 1.0)
        + 0.15 * dims.get("systemic", 0.0) / max(baselines.get("systemic", 1.0), 1.0)
    )

def _composite_daily_load_series(
    sessions: list[dict],
    glossary: list[dict] | None,
    program_start: str,
    current_maxes: dict,
    ref_date: date | None = None,
) -> tuple[list[dict[str, Any]], date | None]:
    daily_fatigue = _daily_fatigue_by_dimension(sessions, glossary, program_start, current_maxes)
    if not daily_fatigue:
        return [], _parse_date(program_start) if program_start else None

    start_day = _parse_date(program_start) if program_start else None
    if start_day is None:
        start_day = min(daily_fatigue.keys())
    end_day = ref_date or date.today()
    if end_day < start_day:
        return [], start_day

    series: list[dict[str, Any]] = []
    day = start_day
    while day <= end_day:
        dims = daily_fatigue.get(day, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        load = _composite_load_from_dimensions(dims)
        series.append(
            {
                "date": day,
                "load": load,
                "axial": dims.get("axial", 0.0),
                "neural": dims.get("neural", 0.0),
                "peripheral": dims.get("peripheral", 0.0),
                "systemic": dims.get("systemic", 0.0),
            }
        )
        day += timedelta(days=1)

    return series, start_day

def _week_start_for_date(day: date, start_day: date) -> date:
    offset = (day - start_day).days
    return start_day + timedelta(days=(offset // 7) * 7)

def _population_sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_val = sum(values) / len(values)
    return math.sqrt(sum((value - mean_val) ** 2 for value in values) / len(values))

def _tsb_label(tsb: float) -> str:
    if tsb < -30:
        return "Deep overload"
    if tsb < -10:
        return "Productive overreach"
    if tsb <= 5:
        return "Building"
    if tsb <= 15:
        return "Peaking window"
    return "Detraining risk"

def _acwr_zone(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.8:
        return "detraining_trend"
    if value <= 1.3:
        return "steady_load"
    if value <= 1.5:
        return "rapid_increase"
    return "load_spike"

def _acwr_label(zone: str, planned_overreach: bool = False) -> str:
    base = _ACWR_ZONE_LABELS.get(zone, "Unknown")
    if planned_overreach and zone != "unknown":
        return f"{base} (expected during planned overreach)"
    return base

def _ewma_acwr_from_daily_loads(
    daily_loads: list[float],
    acute_lambda: float = _ACWR_ACUTE_LAMBDA,
    chronic_lambda: float = _ACWR_CHRONIC_LAMBDA,
) -> float | None:
    if len(daily_loads) < _ACWR_MIN_DAYS:
        return None
    seed = daily_loads[:7]
    seed_mean = sum(seed) / len(seed) if seed else 0.0
    acute = seed_mean
    chronic = seed_mean
    for load in daily_loads[7:]:
        acute = acute_lambda * load + (1 - acute_lambda) * acute
        chronic = chronic_lambda * load + (1 - chronic_lambda) * chronic
    if chronic <= 1e-12:
        return None
    return round(acute / chronic, 3)

def _compute_dimensional_acwr(
    daily_fatigue: dict[date, dict[str, float]],
    phases: list[dict] | None = None,
    current_week: int | None = None,
    program_start: str = "",
    ref_date: date | None = None,
) -> dict:
    """EWMA-based per-dimension ACWR with daily loads and weighted composite."""
    sorted_days = sorted(daily_fatigue.keys())
    if not sorted_days:
        return {
            "status": "insufficient_data",
            "reason": f"Need at least {_ACWR_MIN_DAYS} calendar days of completed training for EWMA ACWR",
        }

    ref = ref_date or date.today()
    start_day = sorted_days[0]
    if ref < start_day:
        return {
            "status": "insufficient_data",
            "reason": "Reference date precedes available training data",
        }

    calendar_days = [start_day + timedelta(days=offset) for offset in range((ref - start_day).days + 1)]
    if len(calendar_days) < _ACWR_MIN_DAYS:
        return {
            "status": "insufficient_data",
            "reason": f"Need at least {_ACWR_MIN_DAYS} calendar days of completed training for EWMA ACWR",
        }

    planned_overreach = _planned_overreach_for_week(phases or [], current_week, program_start)

    dimensions: dict[str, float | None] = {}
    for dim in ("axial", "neural", "peripheral", "systemic"):
        loads = [daily_fatigue.get(day, {}).get(dim, 0.0) for day in calendar_days]
        dimensions[dim] = _ewma_acwr_from_daily_loads(loads)

    valid = {k: v for k, v in dimensions.items() if v is not None}
    composite = round(sum(valid.get(k, 0) * _DIMENSION_WEIGHTS[k] for k in _DIMENSION_WEIGHTS if k in valid), 3) if valid else None
    composite_zone = _acwr_zone(composite)
    return {
        "composite": composite,
        "composite_zone": composite_zone,
        "composite_label": _acwr_label(composite_zone, planned_overreach),
        "dimensions": {
            dim: {
                "value": dimensions[dim],
                "zone": _acwr_zone(dimensions[dim]),
                "label": _acwr_label(_acwr_zone(dimensions[dim]), planned_overreach),
            }
            for dim in ("axial", "neural", "peripheral", "systemic")
        },
    }

def _compute_dimensional_spike(
    weekly_fatigue: dict[int, dict[str, float]],
    deload_weeks: list[int] | None = None,
) -> dict:
    sorted_weeks = sorted(weekly_fatigue.keys())
    if len(sorted_weeks) < 2:
        return {"dimensions": {}, "composite": None}
    dimensions = {}
    for dim in ("axial", "neural", "peripheral", "systemic"):
        vals = [weekly_fatigue[w].get(dim, 0.0) for w in sorted_weeks]
        current = vals[-1]
        prev = vals[:-1][-3:]
        prev_mean = sum(prev) / len(prev) if prev else 0
        spike = _clamp((current - prev_mean) / prev_mean, 0.0, 1.0) if prev_mean > 0 else 0.0
        dimensions[dim] = round(spike, 3)
    valid = {k: v for k, v in dimensions.items() if v is not None}
    composite = round(sum(valid.get(k, 0) * _DIMENSION_WEIGHTS[k] for k in _DIMENSION_WEIGHTS if k in valid), 3) if valid else None
    return {"dimensions": dimensions, "composite": composite}

def estimate_1rm(weight_kg: float, reps: int, rpe: Optional[int] = None) -> dict:
    w = _num(weight_kg)
    e1rm = None
    method = None
    rpe_based = None
    if rpe is not None and 1 <= reps <= 6 and 6 <= int(rpe) <= 10:
        pct = _RPE_TABLE_PRIMARY.get((reps, int(rpe)))
        if pct is not None:
            e1rm = round(w / pct, 1)
            rpe_based = e1rm
            method = "rpe_table"
    elif rpe is None and 1 <= reps <= 5:
        pct = _CONSERVATIVE_REP_PCT.get(reps)
        if pct is not None:
            e1rm = round(w / pct, 1)
            method = "conservative"
    return {"e1rm": e1rm, "method": method, "input_weight_kg": round(w, 1),
            "epley": None, "brzycki": None, "rpe_based": rpe_based}

def calculate_dots(total_kg: float, bodyweight_kg: float, sex: str) -> float:
    sex_key = sex.lower()
    if sex_key not in DOTS_COEFFICIENTS:
        raise ValueError(f"Invalid sex: {sex!r}. Expected 'male' or 'female'.")
    c = DOTS_COEFFICIENTS[sex_key]
    bw = _num(bodyweight_kg)
    total = _num(total_kg)
    denom = c["a"] + c["b"]*bw + c["c"]*bw**2 + c["d"]*bw**3 + c["e"]*bw**4
    if abs(denom) < 1e-12:
        return 0.0
    return round((500 / denom) * total, 2)

def progression_rate(
    sessions: list[dict],
    exercise_name: str,
    program_start: str = "",
    reference_date: date | None = None,
) -> dict:
    """Theil-Sen regression on e1RM per effective training week. Excludes deload/break weeks."""
    if not program_start:
        program_start = _infer_program_start(sessions)

    name_lower = exercise_name.lower()
    ref = reference_date or date.today()
    cutoff = ref - timedelta(days=90)

    ex_sessions = [
        s for s in _get_exercise_sessions(sessions, exercise_name)
        if (d := _parse_date(s.get("date", ""))) is not None and cutoff <= d <= ref
    ]

    deload_info = _detect_deloads(sessions, program_start)
    excluded_weeks: set[int] = {d["week_num"] for d in deload_info if d["is_deload"] or d["is_break"]}
    deload_count = len(excluded_weeks)
    effective_map: dict[int, int] = {
        d["week_num"]: d["effective_index"] for d in deload_info if d["effective_index"] >= 0
    }

    week_e1rm: dict[int, list[float]] = {}
    for s in ex_sessions:
        wk = _session_week_num(s, program_start)
        if wk is None or wk in excluded_weeks:
            continue
        eff_idx = effective_map.get(wk)
        if eff_idx is None:
            continue
        session_rpe = s.get("session_rpe")
        for ex in s.get("exercises", []):
            if ex.get("name", "").lower() != name_lower:
                continue
            if _count_failed_sets(ex) > 0 or _executed_sets(ex) <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or reps <= 0:
                continue
            e1rm = None
            rpe = session_rpe
            if rpe is not None and 1 <= reps <= 6 and 6 <= int(rpe) <= 10:
                pct = _RPE_TABLE_PRIMARY.get((reps, int(rpe)))
                if pct is not None:
                    e1rm = kg / pct
            elif rpe is None and 1 <= reps <= 5:
                pct = _CONSERVATIVE_REP_PCT.get(reps)
                if pct is not None:
                    e1rm = kg / pct
            if e1rm is not None:
                week_e1rm.setdefault(eff_idx, []).append(e1rm)

    if not week_e1rm:
        return {**INSUFFICIENT_DATA, "reason": f"No qualifying e1RM estimates for {exercise_name}"}
    xs = sorted(week_e1rm.keys())
    ys = [max(week_e1rm[w]) for w in xs]
    if len(xs) < 2:
        return {**INSUFFICIENT_DATA, "reason": f"Need at least 2 effective training weeks with {exercise_name} data"}

    result = theilslopes(ys, xs)
    slope, intercept = result[0], result[1]
    kendall_tau, fit_quality = _fit_quality(xs, ys, slope, intercept)

    return {
        "slope_kg_per_week": round(slope, 2),
        "kendall_tau": kendall_tau,
        "fit_quality": fit_quality,
        "r2": fit_quality,
        "r_squared": fit_quality,
        "points": [(round(float(x), 1), round(y, 1)) for x, y in zip(xs, ys)],
        "method": "theilsen",
        "deload_weeks_excluded": deload_count,
    }

def volume_intensity_correlation(sessions: list[dict], exercise_name: str, program_start: str = "") -> dict:
    if not program_start:
        program_start = _infer_program_start(sessions)
    name_lower = exercise_name.lower()
    weekly_volume: dict[int, float] = {}
    weekly_intensity: dict[int, float] = {}
    weekly_count: dict[int, int] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        for ex in s.get("exercises", []):
            if ex.get("name", "").lower() != name_lower:
                continue
            kg = _num(ex.get("kg") or 0)
            sets = _executed_sets(ex)
            reps = _num(ex.get("reps", 0))
            weekly_volume[wk] = weekly_volume.get(wk, 0) + sets * reps * kg
            weekly_intensity[wk] = weekly_intensity.get(wk, 0) + kg
            weekly_count[wk] = weekly_count.get(wk, 0) + 1
    weeks = sorted(weekly_volume.keys())
    if len(weeks) < 3:
        return {**INSUFFICIENT_DATA, "reason": f"Need at least 3 weeks of {exercise_name} data"}
    vol_series = [weekly_volume[w] for w in weeks]
    int_series = [weekly_intensity[w] / weekly_count[w] for w in weeks]
    return {
        "pearson_r": round(_pearson(vol_series, int_series), 3),
        "volume_series": [(w, round(v, 0)) for w, v in zip(weeks, vol_series)],
        "intensity_series": [(w, round(i, 1)) for w, i in zip(weeks, int_series)],
    }

def rpe_drift(
    sessions: list[dict],
    exercise_name: str,
    program_start: str = "",
    window_weeks: int = 4,
    phases: list[dict] | None = None,
) -> dict:
    if not program_start:
        program_start = _infer_program_start(sessions)
    ex_sessions = _get_exercise_sessions(sessions, exercise_name)
    if len(ex_sessions) < 3:
        return {**INSUFFICIENT_DATA, "reason": f"Need at least 3 completed sessions with {exercise_name}"}

    if program_start:
        start_date = _parse_date(program_start)
        window_start = start_date + timedelta(weeks=max(0, (len(sessions) // 3) - window_weeks))
    else:
        window_start = None

    points = []
    for s in ex_sessions:
        if window_start:
            d = _parse_date(s.get("date", ""))
            if d and d < window_start:
                continue
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        rpe = None
        rpe_val = s.get("session_rpe")
        if rpe_val is not None:
            rpe = _num(rpe_val)
        else:
            for ex in s.get("exercises", []):
                if ex.get("name", "").lower() == exercise_name.lower():
                    ex_rpe = ex.get("rpe")
                    rpe = _num(ex_rpe) if ex_rpe is not None else None
                    break
        if rpe is None:
            continue
        points.append((wk, float(rpe)))

    if len(points) < 3:
        return {**INSUFFICIENT_DATA, "reason": f"Need at least 3 RPE data points for {exercise_name}"}

    use_residual = False
    phase_targets: dict[int, float] = {}
    if phases:
        for phase in phases:
            t_min = phase.get("target_rpe_min")
            t_max = phase.get("target_rpe_max")
            if t_min is not None and t_max is not None:
                try:
                    midpoint = (_num(t_min) + _num(t_max)) / 2.0
                    for w in range(int(phase.get("start_week", 0)), int(phase.get("end_week", 0)) + 1):
                        phase_targets[w] = midpoint
                except (ValueError, TypeError):
                    pass
        if phase_targets:
            use_residual = True

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    if use_residual:
        residuals = [(wk, rpe - phase_targets[wk]) for wk, rpe in points if wk in phase_targets]
        if len(residuals) >= 3:
            xs = [r[0] for r in residuals]
            ys = [r[1] for r in residuals]
        else:
            use_residual = False

    if len(xs) >= 2:
        slope, intercept, _, _ = theilslopes(ys, xs)
        kendall_tau, fit_quality = _fit_quality(xs, ys, slope, intercept)
    else:
        slope, kendall_tau, fit_quality = 0.0, 0.0, 0.0

    direction = "up" if slope >= 0.1 else ("down" if slope <= -0.1 else "stable")
    flag = "fatigue" if slope >= 0.1 else ("adaptation" if slope <= -0.1 else None)

    return {
        "slope": round(slope, 3),
        "drift_direction": direction,
        "flag": flag,
        "kendall_tau": kendall_tau,
        "fit_quality": fit_quality,
        "r2": fit_quality,
        "r_squared": fit_quality,
        "mode": "residual" if use_residual else "raw",
    }

def fatigue_index(
    sessions: list[dict],
    days: int = 14,
    glossary: list[dict] | None = None,
    current_maxes: dict | None = None,
    program_start: str = "",
    ref_date: date | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    weeks: int = 1,
    target_rpe_midpoint: float | None = None,
) -> dict:
    ref = ref_date or date.today()
    if window_end:
        end = _parse_date(window_end) or ref
    else:
        end = ref
        
    if window_start:
        start = _parse_date(window_start)
        if start is None:
            start = end - timedelta(days=days)
    else:
        start = end - timedelta(days=days)
        
    history_sessions = [s for s in sessions if (d := _parse_date(s.get("date", ""))) is not None and d <= end and (s.get("completed") or s.get("status") in ("logged", "completed"))]
    
    window_week_count = max(1, math.ceil(((end - start).days + 1) / 7))
    
    if not program_start:
        program_start = _infer_program_start(history_sessions)
    start_day = _parse_date(program_start) if program_start else (min([_parse_date(s.get("date", "")) for s in history_sessions]) if history_sessions else date.today())
    if start_day is None:
        start_day = date.today()
        
    weeks_dict = {}
    for s in history_sessions:
        wk = _session_week_num(s, program_start)
        if wk is not None:
            weeks_dict.setdefault(wk, []).append(s)
            
    deload_info = _detect_deloads(history_sessions, program_start)
    deload_weeks = {d["week_num"] for d in deload_info if d["is_deload"] or d["is_break"]}
    
    weekly_dims = _weekly_fatigue_by_dimension(history_sessions, glossary, program_start, current_maxes or {})
    reservoir_series = _fatigue_reservoir_series(
        history_sessions,
        glossary,
        program_start,
        current_maxes or {},
        end,
    )
    
    def get_baseline_for_week(eval_wk: int) -> tuple[dict[str, float], str]:
        prior = [w for w in sorted(weekly_dims.keys()) if w < eval_wk and w not in deload_weeks]
        if len(prior) >= 6:
            subset = prior[-8:]
            conf = "high"
        elif len(prior) >= 3:
            subset = prior[-5:]
            conf = "medium"
        elif len(prior) > 0:
            subset = prior
            conf = "low"
        else:
            return {"axial": 0, "neural": 0, "peripheral": 0, "systemic": 0}, "low"
            
        b = {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0}
        for dim in b:
            vals = [weekly_dims[w].get(dim, 0) for w in subset]
            vals.sort()
            if len(vals) % 2 == 1:
                b[dim] = vals[len(vals)//2]
            else:
                b[dim] = (vals[len(vals)//2 - 1] + vals[len(vals)//2]) / 2.0
        return b, conf

    weekly_fis = {}
    overload_streaks = {}
    streak = 0
    
    existing_wks = sorted(set(weeks_dict.keys()) | set(weekly_dims.keys()))
    calendar_end_wk = _calendar_week_num(end, start_day)
    calendar_start_wk = min(existing_wks) if existing_wks else 1
    all_wks = list(range(calendar_start_wk, calendar_end_wk + 1))
    for wk in all_wks:
        wk_sessions = weeks_dict.get(wk, [])
        baseline, conf = get_baseline_for_week(wk)
        cur_dims = weekly_dims.get(wk, {"axial": 0, "neural": 0, "peripheral": 0, "systemic": 0})
        
        failed_sets = 0
        total_compound_sets = 0
        for s in wk_sessions:
            for ex in s.get("exercises", []):
                name_lower = ex.get("name", "").lower()
                if any(kw in name_lower for kw in ["squat", "deadlift", "bench", "press", "row", "rdl", "pullup", "chinup"]):
                    sets = _executed_sets(ex)
                    total_compound_sets += sets
                    failed_sets += _count_failed_sets(ex)
        failed_ratio = failed_sets / total_compound_sets if total_compound_sets > 0 else 0
        failure_stress = _clamp(failed_ratio / 0.15, 0, 1)
        
        wk_start_date = start_day + timedelta(days=(wk - 1) * 7)
        wk_end_date = wk_start_date + timedelta(days=6)
        recent_for_spike = [s for s in history_sessions if (d := _parse_date(s.get("date", ""))) and d <= wk_end_date and d >= wk_start_date - timedelta(days=28)]
        wk_fatigue = _weekly_fatigue_by_dimension(recent_for_spike, glossary, program_start, current_maxes or {})
        spike_res = _compute_dimensional_spike(wk_fatigue)
        comp_spike = spike_res.get("composite") or 0.0
        acute_spike_stress = _clamp((comp_spike - 0.05) / 0.35, 0, 1)
        
        rpe_excesses = []
        high_rpes = 0
        total_rpes = 0
        for s in wk_sessions:
            rpe = _num(s.get("session_rpe"))
            if rpe > 0:
                total_rpes += 1
                if target_rpe_midpoint is not None:
                    exc = _clamp((rpe - target_rpe_midpoint) / 2, 0, 1)
                else:
                    exc = _clamp((rpe - 7.0) / 3.0, 0, 1)
                rpe_excesses.append(exc**2)
                if rpe >= 9.0:
                    high_rpes += 1
        rpe_base = math.sqrt(sum(rpe_excesses)/len(rpe_excesses)) if rpe_excesses else 0.0
        rpe_freq = high_rpes / total_rpes if total_rpes > 0 else 0.0
        rpe_stress = _clamp(0.70 * rpe_base + 0.30 * rpe_freq, 0, 1)
        
        reservoir_wk_end_date = start_day + timedelta(days=(wk - 1) * 7 + 6)
        reservoir_wk_end_date = min(reservoir_wk_end_date, end)
        reservoir = _reservoir_stress_for_day(reservoir_series, reservoir_wk_end_date)
        reservoir_stress = reservoir["composite"]
        chronic_load_stress = reservoir_stress
        
        heavy = 0
        very_heavy = 0
        eligible = 0
        for s in wk_sessions:
            for ex in s.get("exercises", []):
                kg = _num(ex.get("kg", 0))
                sets = int(_executed_sets(ex))
                reps = int(_num(ex.get("reps", 0)))
                if sets <= 0 or kg <= 0 or reps <= 0:
                    continue
                name_lower = ex.get("name", "").lower()
                e1rm = None
                if name_lower == "squat": e1rm = (current_maxes or {}).get("squat")
                elif name_lower in ("bench", "bench press"): e1rm = (current_maxes or {}).get("bench")
                elif name_lower == "deadlift": e1rm = (current_maxes or {}).get("deadlift")
                else:
                    if glossary:
                        for g_ex in glossary:
                            if g_ex.get("name", "").lower().strip() == name_lower:
                                raw_e1rm = g_ex.get("e1rm_estimate", g_ex.get("e1rm"))
                                if isinstance(raw_e1rm, dict):
                                    e1rm = (
                                        raw_e1rm.get("kg")
                                        or raw_e1rm.get("e1rm_kg")
                                        or raw_e1rm.get("estimate_kg")
                                        or raw_e1rm.get("value_kg")
                                    )
                                else:
                                    e1rm = raw_e1rm
                                break
                if e1rm and _num(e1rm) > 0:
                    ri = kg / _num(e1rm)
                    eligible += sets
                    if ri >= 0.90:
                        very_heavy += sets
                        heavy += sets
                    elif ri >= 0.85:
                        heavy += sets
        heavy_ratio = heavy / eligible if eligible > 0 else 0
        vheavy_ratio = very_heavy / eligible if eligible > 0 else 0
        intensity_density_stress = _clamp(0.60 * heavy_ratio / 0.35 + 0.40 * vheavy_ratio / 0.15, 0, 1)
        
        monotony_res = compute_monotony_strain(wk_sessions, glossary, program_start, current_maxes)
        monotony = monotony_res.get("monotony", 0)
        strain = monotony_res.get("strain", 0)
        
        strain_hist = []
        for p_wk in range(wk-4, wk):
            if p_wk in weeks_dict:
                m_res = compute_monotony_strain(weeks_dict[p_wk], glossary, program_start, current_maxes)
                if m_res.get("strain") is not None:
                    strain_hist.append(m_res["strain"])
        med_strain = 0
        if strain_hist:
            strain_hist.sort()
            if len(strain_hist) % 2 == 1: med_strain = strain_hist[len(strain_hist)//2]
            else: med_strain = (strain_hist[len(strain_hist)//2 - 1] + strain_hist[len(strain_hist)//2]) / 2.0
            
        m_stress1 = _clamp((monotony - 1.5) / 1.0, 0, 1)
        m_stress2 = _clamp((strain / med_strain - 1.0) / 0.5, 0, 1) if med_strain > 0 else 0
        monotony_stress = max(m_stress1, m_stress2)
        
        acwr_result = compute_acwr(history_sessions, glossary, program_start, current_maxes or {}, ref_date=wk_end_date)
        acwr_val = acwr_result.get("composite", 0) or 0
        is_overload = False
        if wk in deload_weeks:
            is_overload = False
        elif chronic_load_stress >= 0.35:
            is_overload = True
        elif acwr_val >= 1.15:
            is_overload = True
        elif intensity_density_stress >= 0.50:
            is_overload = True
        elif med_strain > 0 and strain >= med_strain * 1.25:
            is_overload = True
        
        if is_overload:
            streak += 1
        else:
            streak = 0
        overload_streak = _clamp(streak / 4, 0, 1)
        overload_streaks[wk] = overload_streak
        
        fi_w = (0.10 * failure_stress + 0.12 * acute_spike_stress + 0.15 * rpe_stress +
                0.34 * chronic_load_stress + 0.10 * overload_streak + 0.10 * intensity_density_stress + 0.09 * monotony_stress)
        fi_w = _clamp(fi_w, 0, 1)
        
        weekly_fis[wk] = {
            "score": fi_w,
            "components": {
                "failure_stress": round(failure_stress, 3),
                "acute_spike_stress": round(acute_spike_stress, 3),
                "rpe_stress": round(rpe_stress, 3),
                "chronic_load_stress": round(chronic_load_stress, 3),
                "overload_streak": round(overload_streak, 3),
                "intensity_density_stress": round(intensity_density_stress, 3),
                "monotony_stress": round(monotony_stress, 3),
                "failed_compound_ratio": round(failed_ratio, 3),
                "composite_spike": round(comp_spike, 3),
                "reservoir_stress": round(reservoir_stress, 3),
                "reservoir_dimension_stress": reservoir["dimensions"],
                "reservoir_max_dimension_stress": reservoir["max_dimension"],
                "reservoir_weighted_stress": reservoir["weighted"],
                "fatigue_context_days_used": reservoir["context_days_used"],
            },
            "conf": reservoir["confidence"] or conf
        }
        
    start_wk = _calendar_week_num(start, start_day)
    end_wk = _calendar_week_num(end, start_day)
    
    window_fis = []
    for wk in range(start_wk, end_wk + 1):
        if wk in weekly_fis:
            window_fis.append((wk, weekly_fis[wk]))
            
    if not window_fis:
        return {**INSUFFICIENT_DATA, "reason": "No data in selected window"}
        
    half_life = _clamp(window_week_count / 2.0, 1, 4)
    weighted_sum = 0
    weight_total = 0
    
    for wk, fi_data in window_fis:
        age_weeks = end_wk - wk
        w = math.exp(-math.log(2) * age_weeks / half_life)
        weighted_sum += fi_data["score"] * w
        weight_total += w
        
    final_fi = weighted_sum / weight_total if weight_total > 0 else 0
    latest_wk_fi = window_fis[-1][1]["score"]
    window_mean = sum(f[1]["score"] for f in window_fis) / len(window_fis)
    window_peak = max(f[1]["score"] for f in window_fis)
    latest_components = window_fis[-1][1]["components"]
    conf = window_fis[-1][1]["conf"]
    
    components = latest_components.copy()
    components.update({
        "latest_week_fi": round(latest_wk_fi, 3),
        "window_mean_fi": round(window_mean, 3),
        "window_peak_fi": round(window_peak, 3),
        "fatigue_window_weeks": window_week_count,
        "fatigue_context_weeks_used": len([w for w in weekly_dims if w < start_wk]),
        "fatigue_context_confidence": conf,
        "fatigue_model": "reservoir_v2",
        "current_state_fi": round(latest_wk_fi, 3),
        "window_weighted_fi": round(final_fi, 3),
    })
    
    score = round(latest_wk_fi, 3)
    
    flags = []
    if components["failed_compound_ratio"] > 0.15: flags.append("failed_sets_spike")
    if components["composite_spike"] > 0.20: flags.append("volume_spike")
    if components["rpe_stress"] > 0.50: flags.append("high_rpe_stress")
    if components["overload_streak"] >= 0.75: flags.append("sustained_overload")
    if components["chronic_load_stress"] >= 0.65: flags.append("high_chronic_load")
    if components.get("reservoir_max_dimension_stress", 0) >= 0.75: flags.append("localized_fatigue_high")
    if components["intensity_density_stress"] >= 0.65: flags.append("high_intensity_density")
    if components["monotony_stress"] >= 0.65: flags.append("high_monotony_strain")
    
    if score >= 0.65: flags.append("overreaching_risk")
    elif score >= 0.45: flags.append("fatigue_high")

    return {
        "score": score,
        "fatigue_model": "reservoir_v2",
        "current_state_fi": round(latest_wk_fi, 3),
        "window_weighted_fi": round(final_fi, 3),
        "window_mean_fi": round(window_mean, 3),
        "window_peak_fi": round(window_peak, 3),
        "weekly_fis": window_fis,
        "components": components,
        "flags": flags,
    }

def _get_session_compliance_stats(session: dict) -> dict:
    planned_exs = session.get("planned_exercises") or []
    actual_exs = session.get("exercises") or []

    if not planned_exs and _is_completed_session(session):
        exec_sets = sum(_executed_sets(ex) for ex in actual_exs)
        exec_reps = sum(_executed_sets(ex) * _num(ex.get("reps", 0)) for ex in actual_exs)
        exec_vol = sum(_executed_volume(ex) for ex in actual_exs)
        return {
            "p_sets": exec_sets, "c_sets": exec_sets,
            "p_reps": exec_reps, "c_reps": exec_reps,
            "p_vol": exec_vol, "c_vol": exec_vol,
        }

    p_sets = sum(_num(ex.get("sets", 0)) for ex in planned_exs)
    p_reps = sum(_num(ex.get("sets", 0)) * _num(ex.get("reps", 0)) for ex in planned_exs)
    p_vol = sum(_num(ex.get("sets", 0)) * _num(ex.get("reps", 0)) * _num(ex.get("kg", 0)) for ex in planned_exs)

    c_sets = sum(_executed_sets(ex) for ex in actual_exs)
    c_reps = sum(_executed_sets(ex) * _num(ex.get("reps", 0)) for ex in actual_exs)
    c_vol = sum(_executed_volume(ex) for ex in actual_exs)

    return {
        "p_sets": p_sets, "c_sets": c_sets,
        "p_reps": p_reps, "c_reps": c_reps,
        "p_vol": p_vol, "c_vol": c_vol,
    }

def session_compliance(sessions: list[dict], phases: list[dict], program_start: str, weeks: int = 4, ref_date: date | None = None) -> dict:
    """All weeks counted — no deload/break exclusions."""
    current_week = _calculate_current_week(program_start, sessions)
    cutoff_week = max(1, current_week - weeks + 1)
    ref = ref_date or date.today()

    sessions_in_window = [
        s for s in sessions
        if (s.get("status") in ("planned", "logged", "completed", "skipped") or not s.get("status"))
        and cutoff_week <= int(s.get("week_number", 0)) <= current_week
    ]
    planned_count = len(sessions_in_window)
    completed_count = sum(1 for s in sessions_in_window if _is_completed_session(s))
    missed_count = sum(
        1 for s in sessions_in_window
        if s.get("status") == "skipped"
        or s.get("_inferred_skipped")
        or (not _is_completed_session(s) and (d := _parse_date(s.get("date", ""))) and d < ref)
    )

    total_p_sets = 0.0
    total_c_sets = 0.0
    total_p_reps = 0.0
    total_c_reps = 0.0
    total_p_vol = 0.0
    total_c_vol = 0.0

    for s in sessions_in_window:
        stats = _get_session_compliance_stats(s)
        total_p_sets += stats["p_sets"]
        total_c_sets += stats["c_sets"]
        total_p_reps += stats["p_reps"]
        total_c_reps += stats["c_reps"]
        total_p_vol += stats["p_vol"]
        total_c_vol += stats["c_vol"]

    compliance_pct = round((completed_count / planned_count) * 100, 1) if planned_count > 0 else 0
    set_compliance_pct = round((total_c_sets / total_p_sets) * 100, 1) if total_p_sets > 0 else (100.0 if completed_count > 0 else 0.0)
    rep_compliance_pct = round((total_c_reps / total_p_reps) * 100, 1) if total_p_reps > 0 else (100.0 if completed_count > 0 else 0.0)
    vol_compliance_pct = round((total_c_vol / total_p_vol) * 100, 1) if total_p_vol > 0 else (100.0 if completed_count > 0 else 0.0)

    current_phase = _find_current_phase(phases, current_week)
    phase_name = current_phase.get("name", "Unknown") if current_phase else "Unknown"

    return {
        "phase": phase_name,
        "planned_sessions": planned_count,
        "completed_sessions": completed_count,
        "missed_sessions": missed_count,
        "compliance_pct": compliance_pct,
        "planned_sets": total_p_sets,
        "completed_sets": total_c_sets,
        "set_compliance_pct": set_compliance_pct,
        "planned_reps": total_p_reps,
        "completed_reps": total_c_reps,
        "rep_compliance_pct": rep_compliance_pct,
        "planned_volume": total_p_vol,
        "completed_volume": total_c_vol,
        "vol_compliance_pct": vol_compliance_pct,
    }

def session_compliance_for_week_window(
    sessions: list[dict],
    phases: list[dict],
    week_start: int,
    week_end: int,
    ref_date: date | None = None,
) -> dict:
    """Compliance for an explicit inclusive training-week range."""
    ref = ref_date or date.today()
    sessions_in_window = [
        s for s in sessions
        if (s.get("status") in ("planned", "logged", "completed", "skipped") or not s.get("status"))
        and week_start <= int(s.get("week_number", 0) or 0) <= week_end
    ]
    planned_count = len(sessions_in_window)
    completed_count = sum(1 for s in sessions_in_window if _is_completed_session(s))
    missed_count = sum(
        1 for s in sessions_in_window
        if s.get("status") == "skipped"
        or s.get("_inferred_skipped")
        or (not _is_completed_session(s) and (d := _parse_date(s.get("date", ""))) and d < ref)
    )

    total_p_sets = 0.0
    total_c_sets = 0.0
    total_p_reps = 0.0
    total_c_reps = 0.0
    total_p_vol = 0.0
    total_c_vol = 0.0

    for s in sessions_in_window:
        stats = _get_session_compliance_stats(s)
        total_p_sets += stats["p_sets"]
        total_c_sets += stats["c_sets"]
        total_p_reps += stats["p_reps"]
        total_c_reps += stats["c_reps"]
        total_p_vol += stats["p_vol"]
        total_c_vol += stats["c_vol"]

    compliance_pct = round((completed_count / planned_count) * 100, 1) if planned_count > 0 else 0
    set_compliance_pct = round((total_c_sets / total_p_sets) * 100, 1) if total_p_sets > 0 else (100.0 if completed_count > 0 else 0.0)
    rep_compliance_pct = round((total_c_reps / total_p_reps) * 100, 1) if total_p_reps > 0 else (100.0 if completed_count > 0 else 0.0)
    vol_compliance_pct = round((total_c_vol / total_p_vol) * 100, 1) if total_p_vol > 0 else (100.0 if completed_count > 0 else 0.0)

    if week_start == week_end:
        phase = _find_current_phase(phases, week_end)
        phase_name = phase.get("name", "Unknown") if phase else "Unknown"
    else:
        phase_names = [
            p.get("name")
            for p in phases
            if p.get("name")
            and p.get("start_week", 0) <= week_end
            and p.get("end_week", 0) >= week_start
        ]
        phase_name = phase_names[-1] if len(set(phase_names)) == 1 else ("Mixed" if phase_names else "Unknown")

    return {
        "phase": phase_name,
        "planned_sessions": planned_count,
        "completed_sessions": completed_count,
        "missed_sessions": missed_count,
        "compliance_pct": compliance_pct,
        "planned_sets": total_p_sets,
        "completed_sets": total_c_sets,
        "set_compliance_pct": set_compliance_pct,
        "planned_reps": total_p_reps,
        "completed_reps": total_c_reps,
        "rep_compliance_pct": rep_compliance_pct,
        "planned_volume": total_p_vol,
        "completed_volume": total_c_vol,
        "vol_compliance_pct": vol_compliance_pct,
    }

def _session_wellness_values(session: dict) -> list[float]:
    wellness = session.get("wellness")
    if not isinstance(wellness, dict):
        return []
    values: list[float] = []
    for key in ("sleep", "soreness", "mood", "stress", "energy"):
        value = wellness.get(key)
        if value is None:
            continue
        num = _num(value)
        if 1 <= num <= 5:
            values.append(num)
    return values

def _readiness_wellness_component(
    sessions: list[dict],
    days: int = 14,
    reference_date: date | None = None,
) -> dict[str, Any]:
    ref = reference_date or date.today()
    cutoff = ref - timedelta(days=days)
    values: list[float] = []
    entries = 0
    for session in sessions:
        d = _parse_date(session.get("date", ""))
        if d is None or d < cutoff or d > ref:
            continue
        session_values = _session_wellness_values(session)
        if not session_values:
            continue
        entries += 1
        values.extend(session_values)
    if not values:
        return {"mean": None, "penalty": 0.5, "entries": 0}
    mean_value = sum(values) / len(values)
    return {
        "mean": round(mean_value, 3),
        "penalty": round(_clamp(1.0 - (mean_value / 5.0), 0.0, 1.0), 3),
        "entries": entries,
    }

def _readiness_performance_trend_component(
    sessions: list[dict],
    current_maxes: dict | None = None,
    days: int = 14,
    reference_date: date | None = None,
) -> dict[str, Any]:
    ref = reference_date or date.today()
    cutoff = ref - timedelta(days=days)
    day_points: dict[date, dict[str, float]] = {}

    for session in sessions:
        if not (session.get("completed") or session.get("status") in ("logged", "completed")):
            continue
        d = _parse_date(session.get("date", ""))
        if d is None or d < cutoff or d > ref:
            continue
        day_lifts = day_points.setdefault(d, {})
        session_rpe = session.get("session_rpe")
        for ex in session.get("exercises", []):
            name_lower = ex.get("name", "").lower().strip()
            canonical = {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}.get(name_lower)
            if canonical is None or _count_failed_sets(ex) > 0 or _executed_sets(ex) <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or reps <= 0:
                continue
            e1rm = _estimate_e1rm_from_set(kg, reps, session_rpe)
            if e1rm is None:
                continue
            if e1rm > day_lifts.get(canonical, float("-inf")):
                day_lifts[canonical] = e1rm

    daily_series: list[tuple[date, float]] = []
    for day, values in sorted(day_points.items()):
        if values:
            daily_series.append((day, sum(values.values()) / len(values)))

    if len(daily_series) < 2:
        return {"slope_kg_per_week": None, "denominator": None, "penalty": 0.5, "points": len(daily_series)}

    xs = [(day - daily_series[0][0]).days / 7.0 for day, _ in daily_series]
    ys = [value for _, value in daily_series]
    slope = theilslopes(ys, xs)[0]

    current_max_values = [
        _num(value)
        for value in (current_maxes or _estimate_maxes_from_sessions(sessions)).values()
        if _num(value) > 0
    ]
    denominator = max(2.5, (sum(current_max_values) / len(current_max_values)) * 0.01) if current_max_values else 2.5
    penalty = _clamp((-slope) / denominator, 0.0, 1.0) if slope < 0 else 0.0

    return {
        "slope_kg_per_week": round(float(slope), 3),
        "denominator": round(float(denominator), 3),
        "penalty": round(float(penalty), 3),
        "points": len(daily_series),
    }

def _next_competition(program: dict, reference_date: date | None = None) -> dict[str, Any] | None:
    ref = reference_date or date.today()
    competitions = sorted(program.get("competitions", []), key=lambda c: c.get("date", ""))
    for comp in competitions:
        if comp.get("status") not in ("confirmed", "optional"):
            continue
        comp_date = _parse_date(comp.get("date", ""))
        if comp_date is not None and comp_date > ref:
            return comp
    meta = program.get("meta", {})
    meta_comp_date = _parse_date(meta.get("comp_date", ""))
    if meta_comp_date is not None and meta_comp_date > ref:
        return {
            "date": meta.get("comp_date"),
            "status": "confirmed",
            "weight_class_kg": meta.get("weight_class_kg"),
        }
    return None

def _readiness_bodyweight_component(
    sessions: list[dict],
    program: dict,
    days: int = 14,
    reference_date: date | None = None,
) -> dict[str, Any]:
    ref = reference_date or date.today()
    cutoff = ref - timedelta(days=days)
    entries: list[tuple[date, float]] = []
    for session in sessions:
        d = _parse_date(session.get("date", ""))
        if d is None or d < cutoff or d > ref:
            continue
        bw = session.get("body_weight_kg")
        if bw is None:
            continue
        entries.append((d, _num(bw)))

    entries.sort(key=lambda item: item[0])
    meta = program.get("meta", {})
    latest_bodyweight = entries[-1][1] if entries else _num(meta.get("current_body_weight_kg", meta.get("bodyweight_kg", 0)))
    if len(entries) < 2:
        return {
            "current_bodyweight_kg": round(latest_bodyweight, 3) if latest_bodyweight > 0 else None,
            "mode": "fallback",
            "expected_weekly_change_kg": None,
            "actual_weekly_change_kg": None,
            "penalty": 0.5,
        }

    recent_entries = entries[-7:]
    xs = [(day - recent_entries[0][0]).days / 7.0 for day, _ in recent_entries]
    ys = [value for _, value in recent_entries]
    actual_weekly_change = theilslopes(ys, xs)[0] if len(recent_entries) >= 2 else 0.0

    upcoming = _next_competition(program, reference_date=ref)
    weight_class = _num(meta.get("weight_class_kg", 0))
    current_bodyweight = recent_entries[-1][1]
    comp_date = _parse_date(upcoming.get("date", "")) if upcoming is not None else None
    if upcoming is not None and comp_date is not None and weight_class > 0 and current_bodyweight > weight_class:
        weeks_to_comp = max((comp_date - ref).days / 7.0, 1 / 7.0)
        if weeks_to_comp <= 6:
            expected_weekly_change = (weight_class - current_bodyweight) / weeks_to_comp
            penalty = _clamp(abs(actual_weekly_change - expected_weekly_change) / 0.5, 0.0, 1.0)
            return {
                "current_bodyweight_kg": round(current_bodyweight, 3),
                "mode": "cut",
                "expected_weekly_change_kg": round(expected_weekly_change, 3),
                "actual_weekly_change_kg": round(float(actual_weekly_change), 3),
                "penalty": round(float(penalty), 3),
                "weeks_to_comp": round(float(weeks_to_comp), 3),
            }

    mean_bw = sum(value for _, value in recent_entries) / len(recent_entries)
    if mean_bw <= 0:
        penalty = 0.5
    else:
        cv = math.sqrt(sum((value - mean_bw) ** 2 for _, value in recent_entries) / len(recent_entries)) / mean_bw
        penalty = _clamp(cv / 0.03, 0.0, 1.0)
    return {
        "current_bodyweight_kg": round(current_bodyweight, 3),
        "mode": "stability",
        "expected_weekly_change_kg": None,
        "actual_weekly_change_kg": round(float(actual_weekly_change), 3),
        "penalty": round(float(penalty), 3),
        "weeks_to_comp": None,
    }

def _estimate_maxes_from_comps(competitions: list[dict], reference_date: date | None = None) -> dict:
    best: dict[str, float] = {}
    ref = reference_date or date.today()
    for c in sorted(competitions, key=lambda c: c.get("date", ""), reverse=True):
        if c.get("status") == "skipped":
            continue
        comp_date = _parse_date(c.get("date", ""))
        if comp_date is None or comp_date > ref:
            continue
        results = c.get("results", {})
        if not results:
            continue
        for lift_key, result_key in [("squat", "squat_kg"), ("bench", "bench_kg"), ("deadlift", "deadlift_kg")]:
            val = results.get(result_key)
            if val is not None:
                try:
                    best[lift_key] = _num(val)
                except (ValueError, TypeError):
                    pass
        if best:
            return best
    return {}

def _estimate_maxes_from_sessions(
    sessions: list[dict],
    lookback_days: int = 42,
    reference_date: date | None = None,
) -> dict:
    """90th percentile of qualifying e1RM estimates over last N days. Min 3 sets/lift."""
    ref = reference_date or date.today()
    cutoff = ref - timedelta(days=lookback_days)
    all_estimates: dict[str, list[float]] = {"squat": [], "bench": [], "deadlift": []}

    for s in sessions:
        d = _parse_date(s.get("date", ""))
        if d is None or d < cutoff or d > ref:
            continue
        if s.get("status", "") in ("planned", "skipped"):
            continue
        session_rpe = s.get("session_rpe")
        for ex in s.get("exercises", []):
            if _count_failed_sets(ex) > 0 or _executed_sets(ex) <= 0:
                continue
            name = ex.get("name", "").lower().strip()
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or reps <= 0:
                continue
            canonical = {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}.get(name)
            if canonical is None:
                continue
            rpe = session_rpe
            e1rm = None
            if rpe is not None and 1 <= reps <= 6 and 6 <= int(rpe) <= 10:
                pct = _RPE_TABLE_PRIMARY.get((reps, int(rpe)))
                if pct is not None:
                    e1rm = kg / pct
            elif rpe is None and 1 <= reps <= 5:
                pct = _CONSERVATIVE_REP_PCT.get(reps)
                if pct is not None:
                    e1rm = kg / pct
            if e1rm is not None:
                all_estimates[canonical].append(round(e1rm, 1))

    result: dict[str, float] = {}
    for lift, vals in all_estimates.items():
        if len(vals) >= 3:
            sorted_vals = sorted(vals)
            idx = min(int(len(sorted_vals) * 0.9), len(sorted_vals) - 1)
            result[lift] = sorted_vals[idx]
    return result if len(result) >= 2 else {}

def _resolve_projection_lambda_multiplier(program: dict, reference_date: date | None = None) -> dict[str, Any]:
    ref = reference_date or date.today()
    competitions = program.get("competitions", []) or []
    prs: list[float] = []

    for comp in sorted(competitions, key=lambda c: c.get("date", ""), reverse=True):
        comp_date = _parse_date(comp.get("date", ""))
        if comp_date is None or comp_date > ref:
            continue
        if comp.get("status") != "completed":
            continue
        results = comp.get("results", {})
        if not isinstance(results, dict):
            continue
        prr = results.get("prr", {})
        if isinstance(prr, dict):
            total_prr = prr.get("total")
            if total_prr is not None:
                value = _num(total_prr)
                if value > 0:
                    prs.append(value)

    meets = len(prs)
    median_prr = round(float(median(prs[:3])), 3) if prs else None
    calibrated = meets >= _PROJECTION_MIN_CALIBRATED_MEETS and median_prr is not None
    lambda_multiplier = (
        round(_clamp(median_prr, _PROJECTION_MIN_MULTIPLIER, _PROJECTION_MAX_MULTIPLIER), 3)
        if calibrated and median_prr is not None
        else None
    )
    return {
        "calibrated": calibrated,
        "meets": meets,
        "median_prr": median_prr,
        "lambda_multiplier": lambda_multiplier,
    }

def compute_prr(results: dict, projected_at_t_minus_1w: dict | None = None) -> dict:
    snapshot = projected_at_t_minus_1w
    if snapshot is None and isinstance(results, dict):
        snapshot = results.get("projected_at_t_minus_1w")
    snapshot = snapshot if isinstance(snapshot, dict) else {}

    prr: dict[str, float | None] = {"squat": None, "bench": None, "deadlift": None, "total": None}
    valid_lifts = 0
    actual_total = 0.0
    projected_total = 0.0

    for lift in ("squat", "bench", "deadlift"):
        actual = _num(results.get(f"{lift}_kg"))
        projected = _num(snapshot.get(f"{lift}_kg"))
        if actual > 0 and projected > 0:
            prr[lift] = round(actual / projected, 3)
            valid_lifts += 1
            actual_total += actual
            projected_total += projected

    if valid_lifts == 3:
        actual_total = _num(results.get("total_kg")) or actual_total
        projected_total = _num(snapshot.get("total_kg")) or projected_total
        if projected_total > 0 and actual_total > 0:
            prr["total"] = round(actual_total / projected_total, 3)

    return prr

def _calendar_week_num(session_date: date, start_day: date) -> int:
    return max(1, ((session_date - start_day).days // 7) + 1)

def compute_volume_landmarks(
    sessions: list[dict],
    glossary: list[dict] | None = None,
    current_maxes: dict | None = None,
    program_start: str = "",
    ref_date: date | None = None,
) -> dict:
    ref = ref_date or date.today()
    if not program_start:
        program_start = _infer_program_start(sessions)
    start_day = _parse_date(program_start)

    eligible_sessions: list[dict] = []
    eligible_dates: list[date] = []
    for session in sessions:
        d = _parse_date(session.get("date", ""))
        if d is None or d > ref:
            continue
        if not (session.get("completed") or session.get("status") in ("logged", "completed")):
            continue
        eligible_sessions.append(session)
        eligible_dates.append(d)

    if len(eligible_sessions) == 0:
        return {
            "squat": {**INSUFFICIENT_DATA, "reason": "Need at least 12 weeks of squat data"},
            "bench": {**INSUFFICIENT_DATA, "reason": "Need at least 12 weeks of bench data"},
            "deadlift": {**INSUFFICIENT_DATA, "reason": "Need at least 12 weeks of deadlift data"},
        }

    if start_day is None:
        start_day = min(eligible_dates)

    current_maxes = current_maxes or _estimate_maxes_from_sessions(eligible_sessions, reference_date=ref)
    deload_info = _detect_deloads(eligible_sessions, program_start)
    excluded_weeks = {d["week_num"] for d in deload_info if d["is_deload"] or d["is_break"]}

    canonical_lifts = {
        "squat": {"squat"},
        "bench": {"bench press", "bench"},
        "deadlift": {"deadlift"},
    }

    result: dict[str, Any] = {}

    for lift, syns in canonical_lifts.items():
        lift_sessions = []
        for s in eligible_sessions:
            has_lift = False
            for ex in s.get("exercises", []):
                if ex.get("name", "").lower().strip() in syns:
                    has_lift = True
                    break
            if has_lift:
                lift_sessions.append(s)

        if not lift_sessions:
            result[lift] = {**INSUFFICIENT_DATA, "reason": f"Need at least {_VOLUME_LANDMARK_MIN_WEEKS} weeks of {lift} data"}
            continue

        week_sessions: dict[int, list[dict]] = {}
        for s in lift_sessions:
            wk = _session_week_num(s, program_start)
            if wk is not None:
                week_sessions.setdefault(wk, []).append(s)

        weeks_data: dict[int, dict[str, Any]] = {}
        for week_num, w_sessions in week_sessions.items():
            if week_num in excluded_weeks:
                continue
            total_sets = sum(
                _executed_sets(ex)
                for s in w_sessions
                for ex in s.get("exercises", [])
                if ex.get("name", "").lower().strip() in syns and _num(ex.get("kg", 0)) > 0 and _num(ex.get("reps", 0)) > 0
            )
            best_e1rm = _best_primary_e1rm_for_sessions(w_sessions)
            weeks_data[week_num] = {
                "sets": total_sets,
                "best_e1rm": best_e1rm,
            }

        week_numbers = sorted(weeks_data.keys())
        history_weeks = len(week_numbers)
        if history_weeks < _VOLUME_LANDMARK_MIN_WEEKS:
            result[lift] = {**INSUFFICIENT_DATA, "reason": f"Need at least {_VOLUME_LANDMARK_MIN_WEEKS} weeks of {lift} data"}
            continue

        delta_records: list[dict[str, Any]] = []
        previous_e1rm: float | None = None
        for week_num in week_numbers:
            week_entry = weeks_data[week_num]
            best_e1rm = week_entry.get("best_e1rm")
            if best_e1rm is None:
                previous_e1rm = None
                continue
            delta = None
            if previous_e1rm is not None:
                delta = float(best_e1rm) - float(previous_e1rm)
            next_week_fi = None
            next_week_readiness = None
            next_week_sessions = week_sessions.get(week_num + 1, [])
            if next_week_sessions:
                next_week_dates = [
                    parsed
                    for s in next_week_sessions
                    if (parsed := _parse_date(s.get("date", ""))) is not None
                ]
                if next_week_dates:
                    next_week_ref = max(next_week_dates)
                    fi_result = fatigue_index(
                        next_week_sessions,
                        days=7,
                        glossary=glossary,
                        current_maxes=current_maxes,
                        program_start=program_start,
                        ref_date=next_week_ref,
                    )
                    if "score" in fi_result:
                        next_week_fi = fi_result["score"]
                    
                    readiness_result = compute_readiness_score(next_week_sessions, program={}, glossary=glossary, program_start=program_start, reference_date=next_week_ref)
                    if "score" in readiness_result:
                        next_week_readiness = readiness_result["score"]

            delta_records.append(
                {
                    "week_num": week_num,
                    "sets": float(week_entry.get("sets", 0.0)),
                    "delta": delta,
                    "next_week_fi": next_week_fi,
                    "next_week_readiness": next_week_readiness,
                }
            )
            previous_e1rm = float(best_e1rm)

        usable_records = [row for row in delta_records if row["delta"] is not None]
        if len(usable_records) < 1:
            result[lift] = {**INSUFFICIENT_DATA, "reason": f"Need at least {_VOLUME_LANDMARK_MIN_WEEKS} weeks of {lift} data"}
            continue

        bin_rows: dict[int, list[dict[str, Any]]] = {}
        for row in usable_records:
            bin_key = int(math.floor(row["sets"] / 2.0) * 2)
            bin_rows.setdefault(bin_key, []).append(row)

        summaries = []
        for bin_key, rows in bin_rows.items():
            avg_sets = sum(float(r["sets"]) for r in rows) / len(rows)
            deltas = [float(r["delta"]) for r in rows if r["delta"] is not None]
            next_fis = [float(r["next_week_fi"]) for r in rows if r["next_week_fi"] is not None]
            next_readiness = [float(r["next_week_readiness"]) for r in rows if r["next_week_readiness"] is not None]
            
            if not deltas:
                continue
                
            prob_neg = len([d for d in deltas if d < 0]) / len(deltas)
            med_fi = None
            if next_fis:
                sorted_fis = sorted(next_fis)
                med_fi = sorted_fis[len(sorted_fis)//2]
                
            med_readiness = None
            if next_readiness:
                sorted_readiness = sorted(next_readiness)
                med_readiness = sorted_readiness[len(sorted_readiness)//2]

            summaries.append(
                {
                    "bin_key": bin_key,
                    "avg_sets": round(avg_sets, 1),
                    "avg_delta": round(sum(deltas) / len(deltas), 3),
                    "prob_neg_delta": prob_neg,
                    "med_next_week_fi": med_fi,
                    "med_next_week_readiness": med_readiness,
                    "count": len(rows),
                }
            )

        if not summaries:
            result[lift] = {**INSUFFICIENT_DATA, "reason": f"Need at least {_VOLUME_LANDMARK_MIN_WEEKS} weeks of {lift} data"}
            continue

        summaries.sort(key=lambda row: row["avg_sets"])
        mv = next((row["avg_sets"] for row in summaries if row["avg_delta"] >= 0), None)
        mev = next((row["avg_sets"] for row in summaries if row["avg_delta"] > 0), None)
        mav_row = max(summaries, key=lambda row: row["avg_delta"])
        
        mrv = None
        for row in summaries:
            count = row["count"]
            med_fi = row["med_next_week_fi"]
            prob_neg = row["prob_neg_delta"]
            med_readiness = row["med_next_week_readiness"]
            
            fi_bad = med_fi is not None and med_fi >= 0.55
            delta_bad = prob_neg is not None and prob_neg >= 0.60
            readiness_bad = med_readiness is not None and med_readiness < 60
            
            if count >= 3 and (fi_bad or delta_bad or readiness_bad):
                mrv = row["avg_sets"]
                break
                
        if mrv is None:
            max_count = max(row["count"] for row in summaries)
            for row in summaries:
                if row["count"] == max_count and row["prob_neg_delta"] >= 0.60:
                    mrv = row["avg_sets"]
                    break

        confidence = "low" if history_weeks <= 17 else ("medium" if history_weeks <= 25 else "high")
        result[lift] = {
            "mv": round(float(mv), 1) if mv is not None else None,
            "mev": round(float(mev), 1) if mev is not None else None,
            "mav": round(float(mav_row["avg_sets"]), 1) if mav_row else None,
            "mrv": round(float(mrv), 1) if mrv is not None else None,
            "confidence": confidence,
            "history_weeks_used": history_weeks,
        }

    return result

def meet_projection(
    program: dict,
    sessions: list[dict],
    comp_date: Optional[str] = None,
    ref_date: date | None = None,
) -> dict:
    """Project competition total. Ceiling scales with time to allow meaningful separation
    between near-term and far-out competitions:
      ceiling_pct = 10% + 0.5% per week beyond 8 (max 20%)
    """
    meta = program.get("meta", {})
    if comp_date is None:
        comp_date = meta.get("comp_date", "")
    if not comp_date:
        return {**INSUFFICIENT_DATA, "reason": "No competition date set"}
    comp = _parse_date(comp_date)
    if comp is None:
        return {**INSUFFICIENT_DATA, "reason": f"Invalid competition date: {comp_date}"}
    ref = ref_date or date.today()
    if comp <= ref:
        return {**INSUFFICIENT_DATA, "reason": "Competition date is in the past"}

    weeks_to_comp = (comp - ref).days / 7.0
    program_start = meta.get("program_start", "")
    if not program_start:
        program_start = _infer_program_start(sessions)

    comp_maxes = _estimate_maxes_from_comps(program.get("competitions", []), reference_date=ref)
    session_maxes = _estimate_maxes_from_sessions(sessions, reference_date=ref)
    maxes = comp_maxes or session_maxes
    if not maxes:
        return {**INSUFFICIENT_DATA, "reason": "No session data to estimate maxes from"}

    projection_calibration = _resolve_projection_lambda_multiplier(program, reference_date=ref)
    lambda_multiplier = projection_calibration.get("lambda_multiplier")

    bodyweight = _num(meta.get("current_body_weight_kg", meta.get("bodyweight_kg", 0)))
    sex = meta.get("sex", "male").lower()
    total_now = sum(_num(maxes.get(k, 0)) for k in ("squat", "bench", "deadlift"))
    dots_now = calculate_dots(total_now, bodyweight, sex) if bodyweight > 0 and total_now > 0 else 0

    if dots_now >= 400:
        base_lambda, peak_factor = 0.85, 1.05
    elif dots_now < 300:
        base_lambda, peak_factor = 0.96, 1.01
    else:
        base_lambda, peak_factor = 0.90, 1.03

    lam = base_lambda
    if isinstance(lambda_multiplier, (int, float)):
        lam = min(base_lambda * float(lambda_multiplier), 0.995)

    weeks_taper = 3 if weeks_to_comp >= 12 else (2 if weeks_to_comp >= 8 else 1)

    deload_info = _detect_deloads(sessions, program_start)
    current_week_num = _calculate_current_week(program_start, sessions)
    comp_week = current_week_num + weeks_to_comp
    remaining_deloads = [w for w in deload_info if w["is_deload"] and current_week_num <= w["week_num"] <= comp_week]
    planned_deload_weeks = len(remaining_deloads)
    if planned_deload_weeks == 0 and weeks_to_comp > 4:
        planned_deload_weeks = int(weeks_to_comp // 4)

    n_t = max(0, weeks_to_comp - weeks_taper - planned_deload_weeks)

    ceiling_pct = min(0.20, 0.10 + (0.005 * max(0.0, weeks_to_comp - 8.0)))

    lifts = {}
    has_real_progression = False
    for lift_name in ("squat", "bench", "deadlift"):
        current = maxes.get(lift_name)
        if current is None:
            continue
        try:
            current_kg = _num(current)
        except (ValueError, TypeError):
            continue

        prog = progression_rate(sessions, lift_name, program_start, reference_date=ref)
        delta_w = prog.get("slope_kg_per_week", 0)
        fit_quality = prog.get("fit_quality", prog.get("r_squared", prog.get("r2", 0)))
        if prog.get("status") != "insufficient_data":
            has_real_progression = True

        lam = min(lam if isinstance(lambda_multiplier, (int, float)) else lam, 0.995)
        projected_gain = delta_w * lam * (1 - lam ** n_t) / (1 - lam) if n_t > 0 and delta_w > 0 and lam < 0.999999 else (delta_w * n_t if n_t > 0 and delta_w > 0 else 0)
        comp_max = (current_kg + projected_gain) * peak_factor

        ceiling = current_kg * (1.0 + ceiling_pct)
        clamped = bool(comp_max > ceiling)
        comp_max = max(current_kg, min(comp_max, ceiling))

        lifts[lift_name] = {
            "current": round(current_kg, 1),
            "projected": round(comp_max, 1),
            "slope_kg_per_week": delta_w,
            "confidence": round(_clamp(fit_quality, 0, 1), 2),
            "ceiling_clamped": clamped,
        }

    if not lifts:
        return {**INSUFFICIENT_DATA, "reason": "No lift maxes found (squat, bench, deadlift)"}
    if not has_real_progression:
        return {**INSUFFICIENT_DATA, "reason": "Insufficient session data to estimate progression"}

    total = sum(v["projected"] for v in lifts.values())
    avg_confidence = sum(v["confidence"] for v in lifts.values()) / len(lifts)

    return {
        "squat": lifts.get("squat", {}).get("projected"),
        "bench": lifts.get("bench", {}).get("projected"),
        "deadlift": lifts.get("deadlift", {}).get("projected"),
        "total": round(total, 1),
        "confidence": round(avg_confidence, 2),
        "weeks_to_comp": round(weeks_to_comp, 1),
        "method": "session_estimated",
        "lifts": lifts,
        "projection_calibration": projection_calibration,
    }

def _lift_stimulus_coefficients(lift_profiles: list[dict] | None) -> dict[str, float]:
    """Return per-lift INOL stimulus multipliers, defaulting to 1.0."""
    coeffs = {"squat": 1.0, "bench": 1.0, "deadlift": 1.0}
    for profile in lift_profiles or []:
        lift = str(profile.get("lift", "")).lower().strip()
        if lift not in coeffs:
            continue
        raw_coeff = profile.get("stimulus_coefficient")
        coeffs[lift] = round(_clamp(_num(raw_coeff) if raw_coeff is not None else 1.0, 1.0, 2.0), 2)
    return coeffs

def compute_e1rm_multiplier_suggestions(
    program: dict,
    max_history: list[dict] | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Suggest per-lift e1RM multipliers based on actual results vs raw session estimates."""
    ref = reference_date or date.today()
    sessions = program.get("sessions", [])
    competitions = program.get("competitions", [])
    lift_profiles = program.get("lift_profiles", [])
    current_multipliers = _lift_e1rm_multipliers(lift_profiles)

    actuals = []
    for c in competitions:
        if c.get("status") == "completed" and (c_date := _parse_date(c.get("date", ""))):
            results = c.get("results", {})
            actuals.append({
                "date": c_date,
                "source": f"Competition: {c.get('name')}",
                "squat": _num(results.get("squat_kg")),
                "bench": _num(results.get("bench_kg")),
                "deadlift": _num(results.get("deadlift_kg")),
            })

    for entry in max_history or []:
        if e_date := _parse_date(entry.get("date", "")):
            actuals.append({
                "date": e_date,
                "source": f"Max History: {entry.get('context', 'Manual')}",
                "squat": _num(entry.get("squat_kg")),
                "bench": _num(entry.get("bench_kg")),
                "deadlift": _num(entry.get("deadlift_kg")),
            })

    ratios_by_lift: dict[str, list[float]] = {"squat": [], "bench": [], "deadlift": []}
    sources_by_lift: dict[str, list[str]] = {"squat": [], "bench": [], "deadlift": []}

    for act in sorted(actuals, key=lambda x: x["date"], reverse=True):
        act_date = act["date"]
        if act_date > ref:
            continue

        raw_estimates = _estimate_maxes_from_sessions(sessions, lookback_days=42, reference_date=act_date)

        for lift in ["squat", "bench", "deadlift"]:
            act_val = act[lift]
            raw_val = raw_estimates.get(lift, 0)

            if act_val > 0 and raw_val > 0:
                ratio = act_val / raw_val
                if 0.80 <= ratio <= 1.15:
                    ratios_by_lift[lift].append(ratio)
                    sources_by_lift[lift].append(act["source"])

    suggestions = {}
    for lift in ["squat", "bench", "deadlift"]:
        ratios = ratios_by_lift[lift]
        current = current_multipliers.get(lift, 1.0)

        if not ratios:
            suggestions[lift] = None
            continue

        suggested = median(ratios)
        clamped = round(_clamp(suggested, 0.85, 1.10), 2)
        diff = round(clamped - current, 2)

        basis = f"Based on {len(ratios)} comparison point(s) from "
        unique_sources = sorted(list(set(sources_by_lift[lift])))
        if len(unique_sources) > 2:
            basis += f"{unique_sources[0]}, {unique_sources[1]}, and {len(unique_sources)-2} more."
        else:
            basis += " and ".join(unique_sources) + "."

        suggestions[lift] = {
            "lift": lift,
            "suggested_multiplier": clamped,
            "current_multiplier": current,
            "difference": diff,
            "basis": basis,
            "sample_size": len(ratios),
        }

    return suggestions

def _lift_inol_thresholds(lift_profiles: list[dict] | None) -> dict[str, dict[str, float]]:
    """Return per-lift INOL thresholds, applying lift-profile overrides when present."""
    thresholds = {lift: dict(bounds) for lift, bounds in _DEFAULT_INOL_THRESHOLDS.items()}
    for profile in lift_profiles or []:
        lift = str(profile.get("lift", "")).lower().strip()
        if lift not in thresholds:
            continue
        low = profile.get("inol_low_threshold")
        high = profile.get("inol_high_threshold")
        if low is not None:
            thresholds[lift]["low"] = round(max(0.0, _num(low)), 2)
        if high is not None:
            thresholds[lift]["high"] = round(max(thresholds[lift]["low"], _num(high)), 2)
        if thresholds[lift]["high"] < thresholds[lift]["low"]:
            thresholds[lift]["high"] = thresholds[lift]["low"]
    return thresholds

def _phase_inol_multiplier(phase: dict | None, effective_week: int | None = None) -> float:
    if not phase:
        return 1.0

    text = f"{phase.get('name', '')} {phase.get('intent', '')}".lower()
    if "deload" in text:
        return 0.45
    if "taper" in text or "peak" in text:
        return 0.65
    if "overreach" in text or _num(phase.get("target_rpe_max")) >= 9:
        return 1.25
    if "hypertrophy" in text or "volume" in text or "accumulation" in text:
        return 1.10
    if "strength" in text:
        return 1.00
    if effective_week is not None and effective_week <= 2:
        return 0.70
    return 1.0

def _inol_uncertainty_multiplier(selected_weeks: int) -> tuple[float, float]:
    if selected_weeks <= 1:
        return 0.75, 1.25
    if selected_weeks <= 2:
        return 0.85, 1.15
    return 1.0, 1.0

def _lift_weekly_volume_ri(
    sessions: list[dict],
    program_start: str,
    current_maxes: dict,
) -> dict[str, dict[int, dict[str, float]]]:
    lift_names = {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}
    result: dict[str, dict[int, dict[str, float]]] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        for ex in s.get("exercises", []):
            canonical = lift_names.get(ex.get("name", "").lower().strip())
            if canonical is None:
                continue
            max_val = _num(current_maxes.get(canonical))
            if max_val <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            sets = int(_executed_sets(ex))
            if kg <= 0 or reps <= 0 or sets <= 0:
                continue
            row = result.setdefault(canonical, {}).setdefault(
                wk,
                {"volume": 0.0, "ri_weighted_sum": 0.0, "ri_sets": 0.0, "avg_ri": 0.0},
            )
            row["volume"] += sets * reps * kg
            row["ri_weighted_sum"] += (kg / max_val) * sets
            row["ri_sets"] += sets

    for lift_weeks in result.values():
        for row in lift_weeks.values():
            row["avg_ri"] = row["ri_weighted_sum"] / row["ri_sets"] if row["ri_sets"] > 0 else 0.0
    return result

def compute_inol(
    sessions: list[dict],
    program_start: str = "",
    current_maxes: dict | None = None,
    lift_profiles: list[dict] | None = None,
    phases: list[dict] | None = None,
    selected_weeks: int = 1,
    all_history_sessions: list[dict] | None = None,
    ref_date: date | None = None,
) -> dict:
    """INOL per lift per week with smoothed singularity handling and per-lift ranges."""
    if not current_maxes:
        current_maxes = _estimate_maxes_from_sessions(all_history_sessions or sessions, reference_date=ref_date)
    if not current_maxes:
        return {**INSUFFICIENT_DATA, "reason": "No current maxes available for INOL calculation"}
    if not program_start:
        program_start = _infer_program_start(all_history_sessions or sessions)

    lift_names = {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}
    stimulus_coefficients = _lift_stimulus_coefficients(lift_profiles)
    thresholds = _lift_inol_thresholds(lift_profiles)
    raw_per_lift_per_week: dict[str, dict[int, float]] = {}
    per_lift_per_week: dict[str, dict[int, float]] = {}

    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        wk = _session_week_num(s, program_start)
        if wk is None:
            continue
        for ex in s.get("exercises", []):
            canonical = lift_names.get(ex.get("name", "").lower().strip())
            if canonical is None:
                continue
            max_val = _num(current_maxes.get(canonical))
            if max_val <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            sets = int(_executed_sets(ex))
            if kg <= 0 or reps <= 0:
                continue
            I = kg / max_val
            denom = math.sqrt(((1 - min(I, _INOL_INTENSITY_CEILING)) ** 2) + (_INOL_EPSILON ** 2))
            inol_contrib = (reps / (100 * denom)) * sets
            coeff = stimulus_coefficients.get(canonical, 1.0)
            adjusted_contrib = inol_contrib * coeff
            raw_per_lift_per_week.setdefault(canonical, {})
            raw_per_lift_per_week[canonical][wk] = raw_per_lift_per_week[canonical].get(wk, 0) + inol_contrib
            per_lift_per_week.setdefault(canonical, {})
            per_lift_per_week[canonical][wk] = per_lift_per_week[canonical].get(wk, 0) + adjusted_contrib

    if not per_lift_per_week:
        return {**INSUFFICIENT_DATA, "reason": "No qualifying sets for INOL"}

    raw_avg_inol = {
        lift: round(sum(weeks_data.values()) / len(weeks_data), 2)
        for lift, weeks_data in raw_per_lift_per_week.items()
        if weeks_data
    }
    avg_inol = {
        lift: round(sum(weeks_data.values()) / len(weeks_data), 2)
        for lift, weeks_data in per_lift_per_week.items()
        if weeks_data
    }
    rounded = {lift: {str(w): round(v, 2) for w, v in sorted(weeks_data.items())}
               for lift, weeks_data in per_lift_per_week.items()}
    raw_rounded = {lift: {str(w): round(v, 2) for w, v in sorted(weeks_data.items())}
                   for lift, weeks_data in raw_per_lift_per_week.items()}

    deload_info = _detect_deloads(all_history_sessions or sessions, program_start)
    effective_map = {
        d["week_num"]: d["effective_index"]
        for d in deload_info
        if not (d["is_deload"] or d["is_break"])
    }
    low_uncertainty, high_uncertainty = _inol_uncertainty_multiplier(selected_weeks)
    phase_adjusted_thresholds: dict[str, dict[str, float]] = {}
    ramp_up_grace: dict[str, bool] = {}
    trend_pressure: dict[str, dict[str, float]] = {}
    weekly_volume_ri = _lift_weekly_volume_ri(
        all_history_sessions or sessions,
        program_start,
        current_maxes or {},
    )

    flags: list[str] = []
    for lift, avg in avg_inol.items():
        selected_lift_weeks = sorted(per_lift_per_week.get(lift, {}).keys())
        latest_week = selected_lift_weeks[-1] if selected_lift_weeks else None
        current_phase = _find_current_phase(phases or [], latest_week or 0)
        effective_week = effective_map.get(latest_week) if latest_week is not None else None
        phase_mult = _phase_inol_multiplier(current_phase, effective_week)
        base_low = thresholds.get(lift, {}).get("low", _DEFAULT_INOL_THRESHOLDS[lift]["low"])
        base_high = thresholds.get(lift, {}).get("high", _DEFAULT_INOL_THRESHOLDS[lift]["high"])
        adjusted_low = base_low * phase_mult
        adjusted_high = base_high * phase_mult
        display_low = adjusted_low * low_uncertainty
        display_high = adjusted_high * high_uncertainty
        phase_adjusted_thresholds[lift] = {
            "low": round(adjusted_low, 2),
            "high": round(adjusted_high, 2),
            "display_low": round(display_low, 2),
            "display_high": round(display_high, 2),
            "phase_multiplier": round(phase_mult, 2),
        }

        phase_text = f"{current_phase.get('name', '')} {current_phase.get('intent', '')}".lower() if current_phase else ""
        grace = effective_week is not None and effective_week <= 2
        if grace and current_phase:
            grace = (
                "overreach" not in phase_text
                and "peak" not in phase_text
                and _num(current_phase.get("target_rpe_max")) < 9
            )
        ramp_up_grace[lift] = bool(grace)

        pressure = 0.0
        volume_ratio = 1.0
        ri_ratio = 1.0
        if latest_week is not None:
            lift_history = weekly_volume_ri.get(lift, {})
            current_row = lift_history.get(latest_week, {})
            prev_weeks = [
                w for w in sorted(lift_history)
                if w < latest_week and lift_history[w].get("volume", 0.0) > 0
            ][-4:]
            prev_volumes = [lift_history[w]["volume"] for w in prev_weeks if lift_history[w].get("volume", 0.0) > 0]
            prev_ris = [lift_history[w]["avg_ri"] for w in prev_weeks if lift_history[w].get("avg_ri", 0.0) > 0]
            if prev_volumes:
                prev_volume_median = median(prev_volumes)
                volume_ratio = (current_row.get("volume", 0.0) / prev_volume_median) if prev_volume_median > 0 else 1.0
            if prev_ris:
                prev_ri_median = median(prev_ris)
                ri_ratio = (current_row.get("avg_ri", 0.0) / prev_ri_median) if prev_ri_median > 0 else 1.0
            pressure = (
                0.60 * _clamp((volume_ratio - 1.0) / 0.50, 0.0, 1.0)
                + 0.40 * _clamp((ri_ratio - 1.0) / 0.15, 0.0, 1.0)
            )

        trend_pressure[lift] = {
            "value": round(pressure, 3),
            "volume_ratio": round(volume_ratio, 3),
            "ri_ratio": round(ri_ratio, 3),
        }

        if avg > display_high and pressure > 0.35:
            flags.append(f"overreaching_risk_{lift}")
        elif avg > display_high:
            flags.append(f"high_inol_monitor_{lift}")
        if avg < display_low and not ramp_up_grace[lift]:
            flags.append(f"low_stimulus_{lift}")

    return {
        "per_lift_per_week": rounded,
        "avg_inol": avg_inol,
        "raw_per_lift_per_week": raw_rounded,
        "raw_avg_inol": raw_avg_inol,
        "stimulus_coefficients": {
            lift: stimulus_coefficients.get(lift, 1.0)
            for lift in avg_inol.keys()
        },
        "thresholds": {
            lift: {
                "low": thresholds.get(lift, {}).get("low", _DEFAULT_INOL_THRESHOLDS[lift]["low"]),
                "high": thresholds.get(lift, {}).get("high", _DEFAULT_INOL_THRESHOLDS[lift]["high"]),
            }
            for lift in avg_inol.keys()
        },
        "phase_adjusted_thresholds": phase_adjusted_thresholds,
        "trend_pressure": trend_pressure,
        "ramp_up_grace": ramp_up_grace,
        "flags": flags,
    }

def compute_acwr(
    sessions: list[dict],
    glossary: list[dict] | None = None,
    program_start: str = "",
    current_maxes: dict | None = None,
    phases: list[dict] | None = None,
    current_week: int | None = None,
    ref_date: date | None = None,
) -> dict:
    """EWMA ACWR per dimension + composite. Returns insufficient_data if < 25 days."""
    if not program_start:
        program_start = _infer_program_start(sessions)
    if not current_maxes:
        current_maxes = _estimate_maxes_from_sessions(sessions)
    if current_week is None:
        current_week = _calculate_current_week(program_start, sessions)

    daily_fatigue = _daily_fatigue_by_dimension(sessions, glossary, program_start, current_maxes or {})
    acwr_result = _compute_dimensional_acwr(
        daily_fatigue,
        phases=phases,
        current_week=current_week,
        program_start=program_start,
        ref_date=ref_date,
    )

    if acwr_result.get("status") == "insufficient_data":
        return acwr_result
    return acwr_result

def compute_banister_ffm(
    sessions: list[dict],
    glossary: list[dict] | None = None,
    program_start: str = "",
    current_maxes: dict | None = None,
    ref_date: date | None = None,
) -> dict:
    if not current_maxes:
        current_maxes = _estimate_maxes_from_sessions(sessions)

    daily_dims = _daily_fatigue_by_dimension(sessions, glossary, program_start, current_maxes or {})
    
    if not daily_dims:
        return {**INSUFFICIENT_DATA, "reason": "No completed training load available for Banister FFM"}

    baselines = _banister_dimension_baselines(
        sessions,
        glossary,
        program_start,
        current_maxes or {},
    )

    daily_series = []
    min_date = min(daily_dims.keys())
    max_date = ref_date or date.today()
    d = min_date
    while d <= max_date:
        dims = daily_dims.get(d, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        norm_load = _normalized_banister_load(dims, baselines)
        daily_series.append({"date": d, "load": norm_load})
        d += timedelta(days=1)
        
    loads = [max(0.0, row["load"]) for row in daily_series]
    if not any(loads):
        return {**INSUFFICIENT_DATA, "reason": "No completed training load available for Banister FFM"}
        
    seed_days = min(_BANISTER_SEED_DAYS, len(loads))
    seed = sum(loads[:seed_days]) / seed_days if seed_days else 0.0
    ctl = seed
    atl = seed

    series = []
    for idx, row in enumerate(daily_series):
        load = loads[idx]
        if idx == 0:
            ctl = seed
            atl = seed
        else:
            ctl = _BANISTER_CTL_LAMBDA * load + (1 - _BANISTER_CTL_LAMBDA) * ctl
            atl = _BANISTER_ATL_LAMBDA * load + (1 - _BANISTER_ATL_LAMBDA) * atl
        tsb = ctl - atl
        series.append(
            {
                "date": row["date"].isoformat(),
                "ctl": round(float(ctl), 3),
                "atl": round(float(atl), 3),
                "tsb": round(float(tsb), 3),
            }
        )

    current = series[-1]
    tsb_today = current["tsb"]
    return {
        "ctl_today": current["ctl"],
        "atl_today": current["atl"],
        "tsb_today": tsb_today,
        "tsb_label": _tsb_label(tsb_today),
        "series": series,
        "load_baselines": {dim: round(value, 3) for dim, value in baselines.items()},
        "model": "normalized_dimension_banister_v2",
    }

def compute_monotony_strain(
    sessions: list[dict],
    glossary: list[dict] | None = None,
    program_start: str = "",
    current_maxes: dict | None = None,
    ref_date: date | None = None,
) -> dict:
    """Foster monotony and strain across program-week buckets."""
    if not current_maxes:
        current_maxes = _estimate_maxes_from_sessions(sessions)

    daily_series, start_day = _composite_daily_load_series(sessions, glossary, program_start, current_maxes or {}, ref_date=ref_date)
    if not daily_series or start_day is None:
        return {"weekly": []}

    week_map: dict[date, list[float]] = {}
    for row in daily_series:
        week_start = _week_start_for_date(row["date"], start_day)
        week_map.setdefault(week_start, []).append(_num(row["load"]))

    weekly: list[dict[str, Any]] = []
    for week_start in sorted(week_map.keys()):
        loads = week_map[week_start]
        weekly_load = sum(loads)
        mean_load = weekly_load / len(loads) if loads else 0.0
        sd_load = _population_sd(loads)
        nonzero_days = sum(1 for value in loads if value > 0)
        denom = max(
            sd_load,
            mean_load * _MONOTONY_RELATIVE_SD_FLOOR,
            _MONOTONY_ABSOLUTE_SD_FLOOR,
        )
        monotony_raw = mean_load / denom if mean_load > 0 else 0.0
        monotony = min(monotony_raw, _MONOTONY_DISPLAY_CAP)
        strain = weekly_load * monotony
        weekly.append(
            {
                "week_start": week_start.isoformat(),
                "monotony": round(float(monotony), 3),
                "monotony_raw": round(float(monotony_raw), 3),
                "strain": round(float(strain), 3),
                "nonzero_training_days": nonzero_days,
                "strain_index": None,
                "flags": [],
            }
        )

    for idx, row in enumerate(weekly):
        flags = row["flags"]
        if row["nonzero_training_days"] >= 3 and row["monotony"] > 2.0:
            flags.append("high_monotony")
        prev_strains = [weekly[i]["strain"] for i in range(max(0, idx - 4), idx)]
        if prev_strains:
            prev_median = median(prev_strains)
            strain_index = row["strain"] / prev_median if prev_median > 0 else None
            row["strain_index"] = round(strain_index, 3) if strain_index is not None else None
            if strain_index is not None and strain_index > 1.5:
                flags.append("strain_spike")

    latest = weekly[-1] if weekly else {}
    return {
        "weekly": weekly,
        "monotony": latest.get("monotony", 0.0),
        "monotony_raw": latest.get("monotony_raw", 0.0),
        "strain": latest.get("strain", 0.0),
        "strain_index": latest.get("strain_index"),
        "nonzero_training_days": latest.get("nonzero_training_days", 0),
    }

def _group_completed_sessions_by_week(
    sessions: list[dict],
    start_day: date,
    ref_date: date,
) -> dict[date, list[dict]]:
    grouped: dict[date, list[dict]] = {}
    for session in sessions:
        if not (session.get("completed") or session.get("status") in ("logged", "completed")):
            continue
        d = _parse_date(session.get("date", ""))
        if d is None or d < start_day or d > ref_date:
            continue
        week_start = _week_start_for_date(d, start_day)
        grouped.setdefault(week_start, []).append(session)
    return grouped

def _canonical_lift_from_name(name: str) -> str | None:
    return {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}.get(name.lower().strip())

def _weekly_sbd_e1rm_total(week_sessions: list[dict]) -> float | None:
    weekly_totals: dict[str, float] = {}
    for session in week_sessions:
        session_rpe = session.get("session_rpe")
        for ex in session.get("exercises", []):
            canonical = _canonical_lift_from_name(ex.get("name", ""))
            if canonical is None:
                continue
            kg = _num(ex.get("kg", 0))
            reps = int(_num(ex.get("reps", 0)))
            if kg <= 0 or reps <= 0:
                continue
            e1rm = _estimate_e1rm_from_set(kg, reps, session_rpe)
            if e1rm is None:
                continue
            weekly_totals[canonical] = max(weekly_totals.get(canonical, 0.0), float(e1rm))
    if not weekly_totals:
        return None
    return sum(weekly_totals.values())

def _weekly_top_intensity(week_sessions: list[dict], current_maxes: dict) -> float | None:
    best = 0.0
    for session in week_sessions:
        for ex in session.get("exercises", []):
            canonical = _canonical_lift_from_name(ex.get("name", ""))
            if canonical is None:
                continue
            max_val = _num(current_maxes.get(canonical, 0))
            if max_val <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            if kg <= 0:
                continue
            best = max(best, kg / max_val)
    return best if best > 0 else None

def compute_decoupling(
    sessions: list[dict],
    glossary: list[dict] | None = None,
    program_start: str = "",
    current_maxes: dict | None = None,
    ref_date: date | None = None,
) -> dict:
    """Trailing 3-week strength-fatigue decoupling."""
    if not current_maxes:
        current_maxes = _estimate_maxes_from_sessions(sessions)

    daily_series, start_day = _composite_daily_load_series(sessions, glossary, program_start, current_maxes or {}, ref_date=ref_date)
    if not daily_series or start_day is None:
        return {**INSUFFICIENT_DATA, "reason": "No completed training load available for decoupling"}

    ref = ref_date or date.today()
    week_sessions = _group_completed_sessions_by_week(sessions, start_day, ref)
    week_starts: list[date] = []
    cursor = start_day
    while cursor <= ref:
        week_starts.append(cursor)
        cursor += timedelta(days=7)

    if len(week_starts) < _DECOUPLING_WINDOW_WEEKS:
        return {**INSUFFICIENT_DATA, "reason": "Need at least 3 weekly training windows for decoupling"}

    points: list[dict[str, Any]] = []
    for idx in range(len(week_starts)):
        if idx + 1 < _DECOUPLING_WINDOW_WEEKS:
            continue
        window_starts = week_starts[idx + 1 - _DECOUPLING_WINDOW_WEEKS: idx + 1]
        e1rm_series: list[float] = []
        fi_series: list[float] = []
        for ws in window_starts:
            sessions_in_week = week_sessions.get(ws, [])
            e1rm_total = _weekly_sbd_e1rm_total(sessions_in_week)
            if e1rm_total is None:
                e1rm_series = []
                fi_series = []
                break
            week_end = min(ws + timedelta(days=6), ref)
            fi_result = fatigue_index(
                sessions,
                days=14,
                glossary=glossary,
                current_maxes=current_maxes or {},
                program_start=program_start,
                ref_date=week_end,
            )
            if "status" in fi_result:
                e1rm_series = []
                fi_series = []
                break
            e1rm_series.append(float(e1rm_total))
            fi_series.append(float(fi_result["score"]))
        if len(e1rm_series) != _DECOUPLING_WINDOW_WEEKS or len(fi_series) != _DECOUPLING_WINDOW_WEEKS:
            continue

        xs = [0.0, 1.0, 2.0]
        slope_e1rm, _, _ = _ols(xs, e1rm_series)
        slope_fi, _, _ = _ols(xs, fi_series)
        baseline_e1rm = e1rm_series[0] if abs(e1rm_series[0]) > 1e-12 else 1e-12
        e1rm_pct = round((slope_e1rm / baseline_e1rm) * 100.0, 3)
        fi_pct_points = round(slope_fi * 100.0, 3)
        decoupling = round(e1rm_pct - fi_pct_points, 3)
        points.append(
            {
                "week_start": window_starts[0].isoformat(),
                "decoupling": decoupling,
                "e1rm_slope_pct_per_week": e1rm_pct,
                "fi_slope_pct_points_per_week": fi_pct_points,
            }
        )

    if not points:
        return {**INSUFFICIENT_DATA, "reason": "No qualifying 3-week windows for decoupling"}

    flags: list[str] = []
    if len(points) >= 3 and all(p["decoupling"] < 0 for p in points[-3:]):
        flags.append("decoupling_fatigue_dominant")

    return {
        "current": points[-1],
        "series": points,
        "flags": flags,
    }

def _find_taper_start(
    program: dict,
    comp_date: date,
    reference_date: date | None = None,
    program_start: str = "",
) -> date | None:
    meta = program.get("meta", {})
    resolved_program_start = _parse_date(meta.get("program_start", "") or program_start) or reference_date
    if resolved_program_start is None:
        return None

    named_taper_start: date | None = None
    for phase in sorted(program.get("phases", []), key=lambda p: int(p.get("start_week", 0) or 0)):
        text = f"{phase.get('name', '')} {phase.get('intent', '')}".lower()
        if "taper" not in text:
            continue
        try:
            start_week = int(phase.get("start_week", 0) or 0)
        except (TypeError, ValueError):
            continue
        if start_week <= 0:
            continue
        phase_start = resolved_program_start + timedelta(weeks=start_week - 1)
        named_taper_start = phase_start
        break

    comp_window_start = comp_date - timedelta(days=21)
    if named_taper_start is None:
        return comp_window_start
    return min(named_taper_start, comp_window_start)

def _window_sums_from_daily_series(
    daily_series: list[dict[str, Any]],
    window_start: date,
    window_end: date,
) -> float:
    total = 0.0
    for row in daily_series:
        day = row["date"]
        if window_start <= day <= window_end:
            total += _num(row["load"])
    return total

def _max_relative_intensity_between(
    sessions: list[dict],
    window_start: date,
    window_end: date,
    current_maxes: dict,
) -> float | None:
    best = 0.0
    for session in sessions:
        if not (session.get("completed") or session.get("status") in ("logged", "completed")):
            continue
        d = _parse_date(session.get("date", ""))
        if d is None or d < window_start or d > window_end:
            continue
        for ex in session.get("exercises", []):
            canonical = _canonical_lift_from_name(ex.get("name", ""))
            if canonical is None:
                continue
            max_val = _num(current_maxes.get(canonical, 0))
            if max_val <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            if kg <= 0:
                continue
            best = max(best, kg / max_val)
    return best if best > 0 else None

def compute_taper_quality(
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None = None,
    current_maxes: dict | None = None,
    program_start: str = "",
    ref_date: date | None = None,
) -> dict | None:
    """Taper quality score for the final 3 weeks before competition."""
    if not current_maxes:
        current_maxes = _estimate_maxes_from_sessions(sessions)

    ref = ref_date or date.today()
    resolved_program_start = program_start or _infer_program_start(sessions)
    upcoming = _next_competition(program, reference_date=ref)
    if upcoming is None:
        return None

    comp_date = _parse_date(upcoming.get("date", ""))
    if comp_date is None:
        return {**INSUFFICIENT_DATA, "reason": "Invalid competition date for taper quality"}

    weeks_to_comp = (comp_date - ref).days / 7.0
    if weeks_to_comp > _TAPER_WINDOW_WEEKS:
        return None
    if weeks_to_comp <= 0:
        return None

    daily_series, _ = _composite_daily_load_series(sessions, glossary, resolved_program_start, current_maxes or {}, ref_date=ref)
    if not daily_series:
        return {**INSUFFICIENT_DATA, "reason": "No completed training load available for taper quality"}

    taper_start = _find_taper_start(
        program,
        comp_date,
        reference_date=_parse_date(resolved_program_start) or daily_series[0]["date"],
        program_start=resolved_program_start,
    )
    if taper_start is None:
        return {**INSUFFICIENT_DATA, "reason": "Could not determine taper start"}
    if taper_start > ref:
        taper_start = ref - timedelta(days=1)

    pre_taper_week_windows: list[tuple[date, date]] = []
    for idx in range(_TAPER_PRE_TAPER_WEEKS, 0, -1):
        window_end = taper_start - timedelta(days=7 * (idx - 1) + 1)
        window_start = window_end - timedelta(days=6)
        pre_taper_week_windows.append((window_start, window_end))

    taper_week_windows: list[tuple[date, date]] = []
    current_start = taper_start
    while current_start <= ref:
        window_end = min(current_start + timedelta(days=6), ref)
        taper_week_windows.append((current_start, window_end))
        current_start = window_end + timedelta(days=1)

    if not taper_week_windows:
        return {**INSUFFICIENT_DATA, "reason": "No taper-period sessions available"}

    pre_taper_week_volumes = []
    for start, end in pre_taper_week_windows:
        raw_volume = _window_sums_from_daily_series(daily_series, start, end)
        window_days = max((end - start).days + 1, 1)
        pre_taper_week_volumes.append(raw_volume * 7.0 / window_days)
    pre_taper_peak_volume = max(pre_taper_week_volumes, default=0.0)
    if pre_taper_peak_volume <= 0:
        return {**INSUFFICIENT_DATA, "reason": "No pre-taper volume baseline available"}

    taper_week_volumes = []
    for start, end in taper_week_windows:
        raw_volume = _window_sums_from_daily_series(daily_series, start, end)
        window_days = max((end - start).days + 1, 1)
        taper_week_volumes.append(raw_volume * 7.0 / window_days)
    taper_weeks_observed = len(taper_week_volumes)
    taper_weekly_volume = sum(taper_week_volumes) / taper_weeks_observed if taper_weeks_observed else 0.0

    volume_reduction = _clamp(
        (pre_taper_peak_volume - taper_weekly_volume) / (pre_taper_peak_volume * 0.5),
        0.0,
        1.0,
    )

    pre_taper_intensity = 0.0
    for start, end in pre_taper_week_windows:
        intensity = _max_relative_intensity_between(sessions, start, end, current_maxes or {})
        if intensity is not None:
            pre_taper_intensity = max(pre_taper_intensity, intensity)

    taper_intensity = 0.0
    for start, end in taper_week_windows:
        intensity = _max_relative_intensity_between(sessions, start, end, current_maxes or {})
        if intensity is not None:
            taper_intensity = max(taper_intensity, intensity)

    if pre_taper_intensity <= 0 or taper_intensity <= 0:
        return {**INSUFFICIENT_DATA, "reason": "No taper intensity baseline available"}

    if taper_intensity >= pre_taper_intensity * _TAPER_INTENSITY_RATIO_FLOOR:
        intensity_maintained = 1.0
    else:
        intensity_maintained = _clamp(
            taper_intensity / (pre_taper_intensity * _TAPER_INTENSITY_RATIO_FLOOR),
            0.0,
            1.0,
        )

    pre_taper_fi_points: list[float] = []
    for start, end in pre_taper_week_windows:
        fi = fatigue_index(
            sessions,
            days=14,
            glossary=glossary,
            current_maxes=current_maxes or {},
            program_start=resolved_program_start,
            ref_date=end,
        )
        if "status" not in fi:
            pre_taper_fi_points.append(float(fi["score"]))

    taper_fi_points: list[float] = []
    for start, end in taper_week_windows:
        fi = fatigue_index(
            sessions,
            days=14,
            glossary=glossary,
            current_maxes=current_maxes or {},
            program_start=resolved_program_start,
            ref_date=end,
        )
        if "status" not in fi:
            taper_fi_points.append(float(fi["score"]))

    if not taper_fi_points:
        return {**INSUFFICIENT_DATA, "reason": "No taper fatigue data available"}

    if len(taper_fi_points) >= 2:
        xs = [float(i) for i in range(len(taper_fi_points))]
        slope_fi, _, _ = _ols(xs, taper_fi_points)
        fatigue_trend = _clamp((-slope_fi) / _TAPER_FI_SLOPE_SCALE, -1.0, 1.0)
    else:
        baseline_fi = median(pre_taper_fi_points) if pre_taper_fi_points else taper_fi_points[0]
        current_fi = taper_fi_points[-1]
        fatigue_trend = _clamp((baseline_fi - current_fi) / _TAPER_FI_DIFF_SCALE, -1.0, 1.0)

    banister = compute_banister_ffm(
        sessions,
        glossary=glossary,
        program_start=resolved_program_start,
        current_maxes=current_maxes or {},
        ref_date=ref,
    )
    if "status" in banister:
        return banister
    tsb_today = float(banister["tsb_today"])
    tsb_component = _clamp((tsb_today + 5) / 20.0, 0.0, 1.0)

    score = _clamp(
        0.30 * volume_reduction
        + 0.25 * intensity_maintained
        + 0.25 * fatigue_trend
        + 0.20 * tsb_component,
        0.0,
        1.0,
    )
    score_pct = round(score * 100.0, 1)

    if score_pct < 40:
        label = "poor"
    elif score_pct < 60:
        label = "acceptable"
    elif score_pct < 80:
        label = "good"
    else:
        label = "excellent"

    return {
        "score": score_pct,
        "label": label,
        "weeks_to_comp": round(float(weeks_to_comp), 3),
        "components": {
            "volume_reduction": round(float(volume_reduction), 3),
            "intensity_maintained": round(float(intensity_maintained), 3),
            "fatigue_trend": round(float(fatigue_trend), 3),
            "tsb": round(float(tsb_component), 3),
        },
    }

def compute_attempt_selection(projected_maxes: dict, attempt_pct: dict | None = None) -> dict | None:
    if not projected_maxes:
        return None
    defaults = {"opener": 0.90, "second": 0.955, "third": 1.00}
    raw_pcts = attempt_pct or defaults
    pcts = {
        lift: _num(raw_pcts.get(lift, default))
        for lift, default in defaults.items()
    }

    def _round_to_2_5(val: float) -> float:
        return round(val / 2.5) * 2.5

    result: dict[str, Any] = {}
    third_total = 0.0
    for lift in ("squat", "bench", "deadlift"):
        c_max = projected_maxes.get(lift)
        if c_max is None:
            continue
        c_max = _num(c_max)
        result[lift] = {
            "opener": _round_to_2_5(c_max * pcts["opener"]),
            "second": _round_to_2_5(c_max * pcts["second"]),
            "third": _round_to_2_5(c_max * pcts["third"]),
        }
        third_total += result[lift]["third"]
    if not result:
        return None
    result["total"] = round(third_total, 1)
    result["attempt_pct_used"] = pcts
    return result

def compute_ri_distribution(sessions: list[dict], current_maxes: dict | None = None) -> dict:
    if not current_maxes:
        return {**INSUFFICIENT_DATA, "reason": "No current maxes for RI distribution"}
    lift_names = {"squat": "squat", "bench press": "bench", "bench": "bench", "deadlift": "deadlift"}

    def _bucket(ri: float) -> str:
        return "heavy" if ri > 0.85 else ("moderate" if ri >= 0.70 else "light")

    overall: dict[str, int] = {"heavy": 0, "moderate": 0, "light": 0}
    per_lift: dict[str, dict[str, int]] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        for ex in s.get("exercises", []):
            canonical = lift_names.get(ex.get("name", "").lower().strip())
            if canonical is None:
                continue
            max_val = current_maxes.get(canonical)
            if not max_val or max_val <= 0:
                continue
            kg = _num(ex.get("kg", 0))
            sets = int(_executed_sets(ex))
            if kg <= 0 or sets <= 0:
                continue
            b = _bucket(kg / max_val)
            overall[b] += sets
            per_lift.setdefault(canonical, {"heavy": 0, "moderate": 0, "light": 0})
            per_lift[canonical][b] += sets

    total = sum(overall.values())
    if total == 0:
        return {**INSUFFICIENT_DATA, "reason": "No qualifying sets for RI distribution"}

    buckets = ["heavy", "moderate", "light"]
    overall_out = {b: {"count": overall[b], "pct": round(overall[b] / total * 100, 1)} for b in buckets}
    per_lift_out = {
        lift: {b: {"count": counts[b], "pct": round(counts[b] / max(sum(counts.values()), 1) * 100, 1)} for b in buckets}
        for lift, counts in per_lift.items()
    }
    return {"overall": overall_out, "per_lift": per_lift_out}

def _specificity_expected_band(weeks_to_comp: float | None) -> dict[str, Any] | None:
    if weeks_to_comp is None or weeks_to_comp < 0:
        return None
    for band in _SPECIFICITY_BANDS:
        min_weeks = band["min_weeks"]
        max_weeks = band["max_weeks"]
        if weeks_to_comp >= min_weeks and (max_weeks is None or weeks_to_comp < max_weeks):
            return band
    return None

def compute_specificity_ratio(
    sessions: list[dict],
    glossary: list[dict] | None = None,
    weeks_to_comp: float | None = None,
) -> dict:
    sbd_names = {"squat", "bench press", "bench", "deadlift"}
    total_sets = sbd_sets = secondary_sets = 0
    category_lookup: dict[str, str] = {}
    if glossary:
        for ex in glossary:
            category_lookup[ex.get("name", "").lower().strip()] = ex.get("category", "")
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        for ex in s.get("exercises", []):
            sets = int(_executed_sets(ex))
            if sets <= 0:
                continue
            name_lower = ex.get("name", "").lower().strip()
            total_sets += sets
            if name_lower in sbd_names:
                sbd_sets += sets
            elif glossary and category_lookup.get(name_lower, "") in ("squat", "bench", "deadlift"):
                secondary_sets += sets
    if total_sets == 0:
        return {**INSUFFICIENT_DATA, "reason": "No working sets for specificity ratio"}

    narrow = round(sbd_sets / total_sets, 3)
    broad = round((sbd_sets + secondary_sets) / total_sets, 3)
    expected_band = _specificity_expected_band(weeks_to_comp)
    narrow_status = "unknown"
    broad_status = "unknown"
    flags: list[str] = []

    if expected_band is not None:
        narrow_min = expected_band["narrow"]["min"]
        narrow_max = expected_band["narrow"]["max"]
        broad_min = expected_band["broad"]["min"]
        broad_max = expected_band["broad"]["max"]

        if narrow < narrow_min:
            narrow_status = "below_expected"
            flags.append("specificity_below_expected")
        elif narrow > narrow_max:
            narrow_status = "above_expected"
            flags.append("specificity_above_expected")
        else:
            narrow_status = "within_expected"

        if broad < broad_min:
            broad_status = "below_expected"
        elif broad > broad_max:
            broad_status = "above_expected"
        else:
            broad_status = "within_expected"

    return {
        "narrow": narrow,
        "broad": broad,
        "total_sets": total_sets,
        "sbd_sets": sbd_sets,
        "secondary_sets": secondary_sets,
        "expected_band": (
            {
                "weeks_to_comp": round(float(weeks_to_comp), 1) if weeks_to_comp is not None else None,
                "narrow": expected_band["narrow"],
                "broad": expected_band["broad"],
            }
            if expected_band is not None
            else None
        ),
        "narrow_status": narrow_status,
        "broad_status": broad_status,
        "flags": flags,
    }

def _select_specificity_target_competition(program: dict, ref_date: date) -> dict[str, Any] | None:
    competitions = [
        c for c in program.get("competitions", [])
        if c.get("status") in ("confirmed", "optional")
        and (d := _parse_date(c.get("date", ""))) is not None
        and d > ref_date
    ]

    if not competitions:
        meta_date = program.get("meta", {}).get("comp_date")
        if meta_date and (d := _parse_date(meta_date)) and d > ref_date:
            return {
                "name": program.get("meta", {}).get("program_name") or "Upcoming Meet",
                "date": meta_date,
                "selection_reason": "meta_comp_date",
            }
        return None

    goal_dates = set()
    for goal in program.get("goals", []) or []:
        if str(goal.get("priority", "")).lower() != "primary":
            continue
        for key in ("target_competition_dates",):
            for value in goal.get(key, []) or []:
                goal_dates.add(str(value))
        if goal.get("target_competition_date"):
            goal_dates.add(str(goal.get("target_competition_date")))

    for comp in sorted(competitions, key=lambda c: c.get("date", "")):
        if comp.get("date") in goal_dates:
            return {**comp, "selection_reason": "primary_goal"}

    for comp in sorted(competitions, key=lambda c: c.get("date", "")):
        notes = str(comp.get("notes", "")).lower()
        if "qualifier" in notes or "primary" in notes:
            return {**comp, "selection_reason": "competition_notes"}

    nearest = sorted(competitions, key=lambda c: c.get("date", ""))[0]
    return {**nearest, "selection_reason": "nearest_confirmed"}

def compute_readiness_score(
    sessions: list[dict],
    program: dict,
    glossary: list[dict] | None = None,
    program_start: str = "",
    reference_date: date | None = None,
) -> dict:
    if not program_start:
        program_start = program.get("meta", {}).get("program_start", "")
    phases = program.get("phases", [])
    ref = reference_date or date.today()
    readiness_sessions = [
        s for s in sessions
        if (d := _parse_date(s.get("date", ""))) is not None and d <= ref
    ]
    current_maxes = _estimate_maxes_from_sessions(readiness_sessions)

    fatigue = fatigue_index(readiness_sessions, days=14, glossary=glossary,
                            current_maxes=current_maxes,
                            program_start=program_start,
                            ref_date=ref)
    f_norm = fatigue.get("score")

    cutoff = ref - timedelta(days=14)
    recent_sessions = [
        s for s in readiness_sessions
        if (d := _parse_date(s.get("date", ""))) is not None and cutoff <= d <= ref
    ]
    rpe_vals = [
        _num(s.get("session_rpe"))
        for s in recent_sessions
        if (s.get("completed") or s.get("status") in ("logged", "completed")) and s.get("session_rpe") is not None
    ]

    current_week = _calculate_current_week(program_start, readiness_sessions)
    current_phase = _find_current_phase(phases, current_week)
    target_rpe_mid = 7.5
    if current_phase:
        t_min = current_phase.get("target_rpe_min")
        t_max = current_phase.get("target_rpe_max")
        if t_min is not None and t_max is not None:
            target_rpe_mid = (_num(t_min) + _num(t_max)) / 2.0
    if rpe_vals:
        avg_rpe = sum(rpe_vals) / len(rpe_vals)
        d_rpe = _clamp((avg_rpe - target_rpe_mid) / 2, 0, 1)
    else:
        d_rpe = None

    wellness = _readiness_wellness_component(readiness_sessions, days=14, reference_date=ref)
    performance = _readiness_performance_trend_component(readiness_sessions, current_maxes=current_maxes, days=14, reference_date=ref)
    bodyweight = _readiness_bodyweight_component(readiness_sessions, program, days=14, reference_date=ref)

    w_subj = wellness.get("penalty") if "reason" not in wellness else None
    p_trend = performance.get("penalty") if "reason" not in performance else None
    s_bw = bodyweight.get("penalty") if "reason" not in bodyweight else None

    def _score_from_penalties(components: list[tuple[float, float]]) -> tuple[float, float]:
        available = sum(w for w, _ in components)
        if available <= 0:
            return 50.0, 0.0
        penalty = sum(w * x for w, x in components) / available
        return round(_clamp((1 - penalty) * 100, 0, 100), 1), round(available, 2)

    training_components = []
    if f_norm is not None: training_components.append((0.45, f_norm))
    if d_rpe is not None: training_components.append((0.30, d_rpe))
    if p_trend is not None: training_components.append((0.25, p_trend))

    external_components = []
    if w_subj is not None: external_components.append((0.60, w_subj))
    if s_bw is not None: external_components.append((0.40, s_bw))

    training_score, training_conf = _score_from_penalties(training_components)
    external_score, external_conf = _score_from_penalties(external_components)

    if training_conf > 0 and external_conf > 0:
        score = round(0.70 * training_score + 0.30 * external_score, 1)
        readiness_confidence = round(0.70 * training_conf + 0.30 * external_conf, 2)
    elif training_conf > 0:
        score = training_score
        readiness_confidence = training_conf
    elif external_conf > 0:
        score = external_score
        readiness_confidence = external_conf
    else:
        score = 50.0
        readiness_confidence = 0.0

    zone = "green" if score > 75 else ("yellow" if score >= 50 else "red")

    return {
        "score": score,
        "training_score": training_score,
        "external_score": external_score,
        "zone": zone,
        "components": {
            "fatigue_norm": round(f_norm, 3) if f_norm is not None else 0.5,
            "rpe_drift": round(d_rpe, 3) if d_rpe is not None else 0.5,
            "wellness": round(w_subj, 3) if w_subj is not None else 0.5,
            "performance_trend": round(p_trend, 3) if p_trend is not None else 0.5,
            "bw_deviation": round(s_bw, 3) if s_bw is not None else 0.5,
        },
        "readiness_confidence": readiness_confidence,
        "training_readiness_confidence": training_conf,
        "external_readiness_confidence": external_conf,
    }

_WEEKLY_ANALYSIS_SECTION_KEYS = {
    "overview",
    "fatigue_readiness",
    "peaking",
    "workload",
    "alerts",
}

def _weekly_analysis_window_context(
    program: dict,
    sessions: list[dict],
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    ref_date: Optional[str] = None,
    week_start: Optional[int] = None,
    week_end: Optional[int] = None,
    weeks: int = 1,
    block: Optional[str] = None,
) -> dict[str, Any]:
    meta = program.get("meta", {})
    phases = program.get("phases", [])
    program_start = meta.get("program_start", "")

    if block:
        sessions = [s for s in sessions if s.get("block", "current") == block]

    current_week = _calculate_current_week(program_start, sessions)
    current_phase = _find_current_phase(phases, current_week)
    phase_name = current_phase.get("name", "Unknown") if current_phase else "Unknown"

    end = _parse_date(window_end) if window_end else (_parse_date(ref_date) if ref_date else date.today())
    ref = end
    start = _parse_date(window_start) if window_start else None
    use_week_window = week_start is not None or week_end is not None or start is None
    selected_week_start: Optional[int] = None
    selected_week_end: Optional[int] = None

    all_sessions_to_ref = [
        s for s in sessions
        if (d := _parse_date(s.get("date", ""))) is not None
        and d <= ref
    ]
    completed_history_to_ref = [
        s for s in all_sessions_to_ref
        if _is_completed_session(s)
    ]

    if use_week_window:
        selected_week_start, selected_week_end = _resolve_week_window(
            sessions,
            current_week,
            weeks,
            program_start,
            week_start=week_start,
            week_end=week_end,
        )
        selected_sessions = _sessions_in_week_window(
            sessions,
            program_start,
            selected_week_start,
            selected_week_end,
        )
        inferred_start, _ = _session_date_bounds(selected_sessions)
        if start is None:
            start = inferred_start or end - timedelta(days=max(7, weeks * 7) - 1)
            window_start = start.isoformat()
        if not window_end:
            window_end = end.isoformat()

        recent_sessions = sorted(
            [
                s for s in selected_sessions
                if (d := _parse_date(s.get("date", ""))) is None or d <= end
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        completed_in_window = sorted(
            [
                s for s in recent_sessions
                if _is_completed_session(s)
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        selected_week_count = max(1, selected_week_end - selected_week_start + 1)
    else:
        cutoff = start
        recent_sessions = sorted(
            [
                s
                for s in all_sessions_to_ref
                if (d := _parse_date(s.get("date", ""))) and d >= cutoff and d <= end
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        completed_in_window = sorted(
            [
                s for s in completed_history_to_ref
                if (d := _parse_date(s.get("date", ""))) is not None
                and cutoff <= d <= end
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        selected_week_nums = {
            wk for s in completed_in_window
            if (wk := _session_week_num(s, program_start)) is not None
        }
        if selected_week_nums:
            selected_week_start = min(selected_week_nums)
            selected_week_end = max(selected_week_nums)
        selected_week_count = max(1, int(weeks or 1))

    return {
        "program": program,
        "sessions": sessions,
        "meta": meta,
        "phases": phases,
        "program_start": program_start,
        "current_week": current_week,
        "current_phase": current_phase,
        "phase_name": phase_name,
        "end": end,
        "ref": ref,
        "window_start": window_start,
        "window_end": window_end,
        "selected_week_start": selected_week_start,
        "selected_week_end": selected_week_end,
        "selected_week_count": selected_week_count,
        "recent_sessions": recent_sessions,
        "completed_in_window": completed_in_window,
        "all_sessions_to_ref": all_sessions_to_ref,
        "completed_history_to_ref": completed_history_to_ref,
    }

def _analysis_exercise_stats(completed_in_window: list[dict]) -> dict[str, dict[str, Any]]:
    exercise_stats: dict[str, dict[str, Any]] = {}
    for s in completed_in_window:
        for ex in s.get("exercises", []):
            name = ex.get("name", "").strip()
            if not name:
                continue
            kg = _num(ex.get("kg", 0))
            sets = _executed_sets(ex)
            reps = _num(ex.get("reps", 0))
            vol = sets * reps * kg
            if sets <= 0:
                continue
            if name not in exercise_stats:
                exercise_stats[name] = {"total_sets": 0, "total_volume": 0.0, "max_kg": 0.0}
            exercise_stats[name]["total_sets"] += int(sets)
            exercise_stats[name]["total_volume"] += vol
            if kg > exercise_stats[name]["max_kg"]:
                exercise_stats[name]["max_kg"] = kg
    for v in exercise_stats.values():
        v["total_volume"] = round(v["total_volume"], 1)
        v["max_kg"] = round(v["max_kg"], 1)
    return exercise_stats

def _analysis_current_maxes(ctx: dict[str, Any]) -> tuple[dict | None, dict | None, dict | None]:
    comp_maxes_raw = _estimate_maxes_from_comps(ctx["program"].get("competitions", []), reference_date=ctx["ref"])
    session_maxes_raw = _estimate_maxes_from_sessions(ctx["completed_history_to_ref"], reference_date=ctx["ref"])
    current_maxes_raw = comp_maxes_raw or session_maxes_raw
    return current_maxes_raw, comp_maxes_raw, session_maxes_raw

def _analysis_current_maxes_out(current_maxes_raw: dict | None, comp_maxes_raw: dict | None, session_maxes_raw: dict | None) -> dict[str, Any]:
    maxes_method = "comp_results" if comp_maxes_raw else ("session_estimated" if session_maxes_raw else "none")
    current_maxes_out: dict[str, Any] = {}
    if current_maxes_raw:
        for lk in ("squat", "bench", "deadlift"):
            val = current_maxes_raw.get(lk)
            if val is not None:
                current_maxes_out[lk] = round(_num(val), 1)
    current_maxes_out["method"] = maxes_method
    return current_maxes_out

def _analysis_target_rpe_midpoint(current_phase: dict | None) -> float | None:
    if not current_phase:
        return None
    t_min = current_phase.get("target_rpe_min")
    t_max = current_phase.get("target_rpe_max")
    if t_min is not None and t_max is not None:
        return (_num(t_min) + _num(t_max)) / 2.0
    return None

def _analysis_compliance_obj(ctx: dict[str, Any]) -> dict[str, Any]:
    if ctx["selected_week_start"] is not None and ctx["selected_week_end"] is not None:
        compliance_result = session_compliance_for_week_window(
            ctx["sessions"],
            ctx["phases"],
            ctx["selected_week_start"],
            ctx["selected_week_end"],
            ref_date=ctx["ref"],
        )
    else:
        compliance_result = session_compliance(
            ctx["sessions"],
            ctx["phases"],
            ctx["program_start"],
            weeks=ctx["selected_week_count"],
            ref_date=ctx["ref"],
        )
    return {
        "phase": compliance_result.get("phase", "Unknown"),
        "planned": compliance_result.get("planned_sessions", 0),
        "completed": compliance_result.get("completed_sessions", 0),
        "missed": compliance_result.get("missed_sessions", 0),
        "pct": compliance_result.get("compliance_pct", 0),
        "planned_sets": compliance_result.get("planned_sets", 0),
        "completed_sets": compliance_result.get("completed_sets", 0),
        "set_pct": compliance_result.get("set_compliance_pct", 0),
        "planned_reps": compliance_result.get("planned_reps", 0),
        "completed_reps": compliance_result.get("completed_reps", 0),
        "rep_pct": compliance_result.get("rep_compliance_pct", 0),
        "planned_volume": compliance_result.get("planned_volume", 0),
        "completed_volume": compliance_result.get("completed_volume", 0),
        "vol_pct": compliance_result.get("vol_compliance_pct", 0),
    }

def _analysis_deload_info(ctx: dict[str, Any]) -> dict[str, Any]:
    deload_info_raw = _detect_deloads(ctx["sessions"], ctx["program_start"])
    return {
        "deload_weeks": [d["week_num"] for d in deload_info_raw if d["is_deload"]],
        "break_weeks": [d["week_num"] for d in deload_info_raw if d["is_break"]],
        "effective_training_weeks": sum(1 for d in deload_info_raw if d["effective_index"] >= 0),
    }

def _analysis_projection_payload(ctx: dict[str, Any], current_maxes_out: dict[str, Any]) -> dict[str, Any]:
    program = ctx["program"]
    sessions = ctx["sessions"]
    meta = ctx["meta"]
    ref = ctx["ref"]
    end = ctx["end"]

    estimated_dots = None
    estimated_dots_reason = None
    bodyweight = _num(
        meta.get(
            "current_body_weight_kg",
            meta.get("bodyweight_kg", meta.get("body_weight_kg", 0)),
        )
    )
    sex = str(
        meta.get("sex")
        or program.get("settings", {}).get("sex")
        or ""
    ).lower()
    if bodyweight > 0 and sex in ("male", "female") and all(current_maxes_out.get(lk, 0) for lk in ("squat", "bench", "deadlift")):
        total_kg = sum(current_maxes_out.get(lk, 0) for lk in ("squat", "bench", "deadlift"))
        if total_kg > 0:
            estimated_dots = calculate_dots(total_kg, bodyweight, sex)
    else:
        estimated_dots_reason = "Missing sex or bodyweight"

    projections: list[dict[str, Any]] = []
    projection_reason = None
    upcoming = [
        c for c in sorted(program.get("competitions", []), key=lambda x: x.get("date", ""))
        if c.get("status") in ("confirmed", "optional", "completed") and (d := _parse_date(c.get("date", ""))) and d > ref
    ]
    to_project = [upcoming[0], upcoming[-1]] if len(upcoming) >= 2 else upcoming[:1]
    projection_calibration = _resolve_projection_lambda_multiplier(program, reference_date=ref)

    for comp in to_project:
        proj = meet_projection(program, sessions, comp_date=comp["date"], ref_date=end)
        if "total" in proj:
            projections.append({
                "total": proj["total"],
                "confidence": proj["confidence"],
                "weeks_to_comp": proj.get("weeks_to_comp"),
                "method": proj.get("method"),
                "comp_name": comp.get("name"),
                "lifts": proj.get("lifts", {}),
                "projection_calibration": proj.get("projection_calibration"),
            })

    if not projections and not to_project and meta.get("comp_date"):
        proj = meet_projection(program, sessions, comp_date=meta["comp_date"], ref_date=end)
        if "total" in proj:
            projections.append({"total": proj["total"], "confidence": proj["confidence"],
                                 "weeks_to_comp": proj.get("weeks_to_comp"), "method": proj.get("method"),
                                 "comp_name": None, "lifts": proj.get("lifts", {}),
                                 "projection_calibration": proj.get("projection_calibration")})
        else:
            projection_reason = proj.get("reason", "Insufficient data for projection")

    attempt_selection = None
    if projections:
        attempt_pct = meta.get("attempt_pct")
        first_proj_lifts = projections[0].get("lifts", {})
        projected_maxes = {
            lift: data.get("projected") for lift, data in first_proj_lifts.items()
            if isinstance(data, dict) and data.get("projected") is not None
        }
        if projected_maxes:
            attempt_selection = compute_attempt_selection(projected_maxes, attempt_pct)

    return {
        "estimated_dots": estimated_dots,
        "estimated_dots_reason": estimated_dots_reason,
        "projections": projections,
        "projection_reason": projection_reason,
        "projection_calibration": projection_calibration,
        "attempt_selection": attempt_selection,
    }

def _analysis_workload_payload(ctx: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    completed_in_window = ctx["completed_in_window"]
    sessions = ctx["sessions"]
    program_start = ctx["program_start"]
    phases = ctx["phases"]
    end = ctx["end"]
    exercise_stats = _analysis_exercise_stats(completed_in_window)
    exercise_names = {ex.get("name", "").lower().strip() for s in completed_in_window for ex in s.get("exercises", []) if ex.get("name") and _executed_sets(ex) > 0}
    tracked_lifts = []
    lift_alias_map = {}
    for canonical, output_key in [("squat", "squat"), ("bench press", "bench"), ("deadlift", "deadlift"), ("bench", "bench")]:
        if canonical in exercise_names and output_key not in lift_alias_map:
            lift_alias_map[output_key] = canonical
            if output_key not in tracked_lifts:
                tracked_lifts.append(output_key)

    lifts_report = {}
    flags: list[str] = []
    for lift_key in tracked_lifts:
        ex_name = lift_alias_map.get(lift_key, lift_key)
        lift_data: dict[str, Any] = {}

        prog = progression_rate(sessions, ex_name, program_start, reference_date=end)
        if "slope_kg_per_week" in prog:
            lift_data["progression_rate_kg_per_week"] = prog["slope_kg_per_week"]
            lift_data["fit_quality"] = prog.get("fit_quality")
            lift_data["kendall_tau"] = prog.get("kendall_tau")
            lift_data["r2"] = prog.get("r2")
            lift_data["r_squared"] = prog.get("r_squared")
        else:
            lift_data["progression_rate_kg_per_week"] = None
            lift_data["fit_quality"] = None
            lift_data["kendall_tau"] = None
            lift_data["r2"] = None
            lift_data["r_squared"] = None

        vol_corr = volume_intensity_correlation(sessions, ex_name, program_start)
        if "volume_series" in vol_corr and len(vol_corr["volume_series"]) >= 2:
            vols = [v[1] for v in vol_corr["volume_series"]]
            intens = [i[1] for i in vol_corr["intensity_series"]]
            prev_vol = vols[-2]
            prev_int = intens[-2]
            lift_data["volume_change_pct"] = round(((vols[-1] - prev_vol) / prev_vol * 100) if prev_vol > 0 else 0, 1)
            lift_data["intensity_change_pct"] = round(((intens[-1] - prev_int) / prev_int * 100) if prev_int > 0 else 0, 1)

        drift = rpe_drift(sessions, ex_name, program_start, phases=phases)
        if "drift_direction" in drift:
            lift_data["rpe_trend"] = drift["drift_direction"]
            if drift.get("flag"):
                flags.append(f"{ex_name}_rpe_{drift['flag']}")
        else:
            lift_data["rpe_trend"] = "unknown"

        lift_data["failed_sets"] = int(sum(
            _count_failed_sets(ex)
            for s in completed_in_window
            for ex in s.get("exercises", [])
            if ex.get("name", "").lower().strip() == ex_name
        ))
        lift_data["executed_sets"] = int(sum(
            _executed_sets(ex)
            for s in completed_in_window
            for ex in s.get("exercises", [])
            if ex.get("name", "").lower().strip() == ex_name
        ))
        lift_data["planned_sets"] = int(sum(
            _num(ex.get("sets", 0))
            for s in completed_in_window
            for ex in s.get("exercises", [])
            if ex.get("name", "").lower().strip() == ex_name
        ))
        lift_data["max_kg"] = round(float(max([_num(ex.get("kg", 0)) for s in completed_in_window for ex in s.get("exercises", []) if ex.get("name", "").lower().strip() == ex_name and _executed_sets(ex) > 0] or [0.0])), 1)
        lift_data["total_volume"] = round(float(sum([_executed_volume(ex) for s in completed_in_window for ex in s.get("exercises", []) if ex.get("name", "").lower().strip() == ex_name])), 1)
        lifts_report[ex_name] = lift_data

    return {"lifts": lifts_report, "exercise_stats": exercise_stats}, flags

def weekly_analysis_section(
    program: dict,
    sessions: list[dict],
    section: str,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    ref_date: Optional[str] = None,
    week_start: Optional[int] = None,
    week_end: Optional[int] = None,
    weeks: int = 1,
    block: Optional[str] = None,
    glossary: list[dict] | None = None,
) -> dict:
    """Compute one weekly analysis section without building the full report."""
    section = str(section or "").strip()
    if section not in _WEEKLY_ANALYSIS_SECTION_KEYS:
        raise ValueError(f"Unknown weekly analysis section: {section}")

    ctx = _weekly_analysis_window_context(
        program,
        sessions,
        window_start=window_start,
        window_end=window_end,
        ref_date=ref_date,
        week_start=week_start,
        week_end=week_end,
        weeks=weeks,
        block=block,
    )
    current_maxes_raw, comp_maxes_raw, session_maxes_raw = _analysis_current_maxes(ctx)
    current_maxes_out = _analysis_current_maxes_out(current_maxes_raw, comp_maxes_raw, session_maxes_raw)

    if section == "overview":
        return {
            "week": ctx["current_week"],
            "selected_week_start": ctx["selected_week_start"],
            "selected_week_end": ctx["selected_week_end"],
            "selected_week_count": ctx["selected_week_count"],
            "window_start": ctx["window_start"],
            "window_end": ctx["window_end"],
            "selected_session_context": ctx["recent_sessions"],
            "block": ctx["phase_name"],
            "compliance": _analysis_compliance_obj(ctx),
            "current_maxes": current_maxes_out,
            **_analysis_projection_payload(ctx, current_maxes_out),
            "sessions_analyzed": len(ctx["completed_in_window"]),
            "deload_info": _analysis_deload_info(ctx),
        }

    if section == "workload":
        payload, _ = _analysis_workload_payload(ctx)
        return payload

    if section == "fatigue_readiness":
        target_rpe_mid = _analysis_target_rpe_midpoint(ctx["current_phase"])
        fatigue = fatigue_index(
            ctx["completed_history_to_ref"],
            days=ctx["selected_week_count"] * 7,
            glossary=glossary,
            current_maxes=current_maxes_raw,
            program_start=ctx["program_start"],
            ref_date=ctx["ref"],
            window_start=ctx["window_start"],
            window_end=ctx["window_end"],
            weeks=ctx["selected_week_count"],
            target_rpe_midpoint=target_rpe_mid,
        )
        fatigue_score = fatigue.get("score") if "score" in fatigue else None
        fatigue_components = fatigue.get("components", {}) if "components" in fatigue else {}

        fatigue_dimensions = None
        if glossary is not None:
            weekly_dim = _weekly_fatigue_by_dimension(ctx["completed_in_window"], glossary, ctx["program_start"], current_maxes_raw or {})
            acwr_for_dimensions = compute_acwr(
                ctx["completed_history_to_ref"],
                glossary,
                ctx["program_start"],
                current_maxes_raw or {},
                phases=ctx["phases"],
                current_week=ctx["current_week"],
                ref_date=ctx["end"],
            )
            spike = _compute_dimensional_spike(weekly_dim)
            weekly_rounded = {wk: {k: round(v, 1) for k, v in dims.items()} for wk, dims in sorted(weekly_dim.items())}
            fatigue_dimensions = {
                "weekly": weekly_rounded,
                "acwr": acwr_for_dimensions,
                "spike": spike,
                "dimension_weights": _DIMENSION_WEIGHTS,
                "label": "selected_window_dimensions_current_state_acwr",
            }

        inol_result = compute_inol(
            ctx["completed_in_window"],
            ctx["program_start"],
            current_maxes_raw,
            ctx["program"].get("lift_profiles"),
            phases=ctx["phases"],
            selected_weeks=ctx["selected_week_count"],
            all_history_sessions=ctx["completed_history_to_ref"],
            ref_date=ctx["end"],
        )
        acwr_result = compute_acwr(
            ctx["completed_history_to_ref"],
            glossary,
            ctx["program_start"],
            current_maxes_raw,
            phases=ctx["phases"],
            current_week=ctx["current_week"],
            ref_date=ctx["end"],
        )
        ri_result = compute_ri_distribution(ctx["completed_in_window"], current_maxes_raw)
        volume_landmarks = compute_volume_landmarks(
            ctx["completed_history_to_ref"],
            glossary,
            current_maxes_raw or {},
            ctx["program_start"],
            ref_date=ctx["end"],
        )
        readiness_result = compute_readiness_score(
            ctx["all_sessions_to_ref"],
            ctx["program"],
            glossary,
            ctx["program_start"],
            reference_date=ctx["ref"],
        )

        return {
            "fatigue_index": fatigue_score,
            "fatigue_components": fatigue_components,
            "fatigue_dimensions": fatigue_dimensions,
            "inol": inol_result if "status" not in inol_result else None,
            "acwr": acwr_result,
            "ri_distribution": ri_result if "status" not in ri_result else None,
            "volume_landmarks": volume_landmarks,
            "readiness_score": readiness_result,
        }

    if section == "peaking":
        banister = None
        monotony_strain = None
        decoupling = None
        taper_quality = None
        if glossary is not None:
            banister = compute_banister_ffm(
                ctx["completed_history_to_ref"],
                glossary,
                ctx["program_start"],
                current_maxes_raw or {},
                ref_date=ctx["end"],
            )
            monotony_strain = compute_monotony_strain(
                ctx["completed_history_to_ref"],
                glossary,
                ctx["program_start"],
                current_maxes_raw or {},
                ref_date=ctx["end"],
            )
            decoupling = compute_decoupling(
                ctx["completed_history_to_ref"],
                glossary,
                ctx["program_start"],
                current_maxes_raw or {},
                ref_date=ctx["end"],
            )
            taper_quality = compute_taper_quality(
                ctx["program"],
                ctx["completed_history_to_ref"],
                glossary,
                current_maxes_raw or {},
                ctx["program_start"],
                ref_date=ctx["end"],
            )
        specificity_target = _select_specificity_target_competition(ctx["program"], ctx["ref"])
        specificity_comp_date = specificity_target.get("date") if specificity_target else None
        specificity_weeks_to_comp = None
        if specificity_comp_date:
            comp_dt = _parse_date(specificity_comp_date)
            if comp_dt is not None and comp_dt > ctx["ref"]:
                specificity_weeks_to_comp = (comp_dt - ctx["ref"]).days / 7.0
        specificity_result = compute_specificity_ratio(
            ctx["completed_in_window"],
            glossary,
            weeks_to_comp=specificity_weeks_to_comp,
        )
        peaking_timeline = _build_peaking_timeline(
            ctx["program"],
            ctx["sessions"],
            glossary,
            ctx["ref"],
            banister,
            current_maxes_raw or {},
        )
        return {
            "banister": banister,
            "monotony_strain": monotony_strain,
            "decoupling": decoupling,
            "taper_quality": taper_quality,
            "specificity_ratio": specificity_result if "status" not in specificity_result else None,
            "specificity_target_competition": specificity_target,
            "peaking_timeline": peaking_timeline,
        }

    _, workload_flags = _analysis_workload_payload(ctx)
    all_flags = list(workload_flags)

    target_rpe_mid = _analysis_target_rpe_midpoint(ctx["current_phase"])
    fatigue = fatigue_index(
        ctx["completed_history_to_ref"],
        days=ctx["selected_week_count"] * 7,
        glossary=glossary,
        current_maxes=current_maxes_raw,
        program_start=ctx["program_start"],
        ref_date=ctx["ref"],
        window_start=ctx["window_start"],
        window_end=ctx["window_end"],
        weeks=ctx["selected_week_count"],
        target_rpe_midpoint=target_rpe_mid,
    )
    fatigue_score = fatigue.get("score") if "score" in fatigue else None
    if fatigue.get("flags"):
        all_flags.extend(fatigue["flags"])
    projection_payload = _analysis_projection_payload(ctx, current_maxes_out)
    acwr_result = compute_acwr(
        ctx["completed_history_to_ref"],
        glossary,
        ctx["program_start"],
        current_maxes_raw,
        phases=ctx["phases"],
        current_week=ctx["current_week"],
        ref_date=ctx["end"],
    )
    readiness_result = compute_readiness_score(
        ctx["all_sessions_to_ref"],
        ctx["program"],
        glossary,
        ctx["program_start"],
        reference_date=ctx["ref"],
    )
    banister = None
    monotony_strain = None
    decoupling = None
    if glossary is not None:
        banister = compute_banister_ffm(
            ctx["completed_history_to_ref"],
            glossary,
            ctx["program_start"],
            current_maxes_raw or {},
            ref_date=ctx["end"],
        )
        monotony_strain = compute_monotony_strain(
            ctx["completed_history_to_ref"],
            glossary,
            ctx["program_start"],
            current_maxes_raw or {},
            ref_date=ctx["end"],
        )
        decoupling = compute_decoupling(
            ctx["completed_history_to_ref"],
            glossary,
            ctx["program_start"],
            current_maxes_raw or {},
            ref_date=ctx["end"],
        )
    inol_result = compute_inol(
        ctx["completed_in_window"],
        ctx["program_start"],
        current_maxes_raw,
        ctx["program"].get("lift_profiles"),
        phases=ctx["phases"],
        selected_weeks=ctx["selected_week_count"],
        all_history_sessions=ctx["completed_history_to_ref"],
        ref_date=ctx["end"],
    )
    if "flags" in inol_result and inol_result["flags"]:
        all_flags.extend([flag for flag in inol_result["flags"] if flag not in all_flags])
    if isinstance(monotony_strain, dict):
        for row in monotony_strain.get("weekly", []):
            for flag in row.get("flags", []):
                if flag not in all_flags:
                    all_flags.append(flag)
    if isinstance(decoupling, dict) and "flags" in decoupling:
        for flag in decoupling["flags"]:
            if flag not in all_flags:
                all_flags.append(flag)
    specificity_target = _select_specificity_target_competition(ctx["program"], ctx["ref"])
    specificity_comp_date = specificity_target.get("date") if specificity_target else None
    specificity_weeks_to_comp = None
    if specificity_comp_date:
        comp_dt = _parse_date(specificity_comp_date)
        if comp_dt is not None and comp_dt > ctx["ref"]:
            specificity_weeks_to_comp = (comp_dt - ctx["ref"]).days / 7.0
    specificity_result = compute_specificity_ratio(
        ctx["completed_in_window"],
        glossary,
        weeks_to_comp=specificity_weeks_to_comp,
    )
    alerts = generate_alerts(
        {
            "week": ctx["current_week"],
            "fatigue_index": fatigue_score,
            "current_maxes": current_maxes_out,
            "projections": projection_payload["projections"],
            "banister": banister,
            "acwr": acwr_result,
            "decoupling": decoupling,
            "specificity_ratio": specificity_result if "status" not in specificity_result else None,
            "monotony_strain": monotony_strain,
            "readiness_score": readiness_result,
        },
        ctx["program"],
        ctx["completed_history_to_ref"],
        glossary,
        ref_date=ctx["end"],
        window_weeks=ctx["selected_week_count"],
    )
    return {
        "alerts": alerts,
        "flags": all_flags,
    }

def weekly_analysis(
    program: dict,
    sessions: list[dict],
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    ref_date: Optional[str] = None,
    week_start: Optional[int] = None,
    week_end: Optional[int] = None,
    weeks: int = 1,
    block: Optional[str] = None,
    glossary: list[dict] | None = None,
) -> dict:
    """Full weekly analysis — single entry point for tools and API."""
    meta = program.get("meta", {})
    phases = program.get("phases", [])
    program_start = meta.get("program_start", "")

    if block:
        sessions = [s for s in sessions if s.get("block", "current") == block]

    current_week = _calculate_current_week(program_start, sessions)
    current_phase = _find_current_phase(phases, current_week)
    phase_name = current_phase.get("name", "Unknown") if current_phase else "Unknown"

    end = _parse_date(window_end) if window_end else (_parse_date(ref_date) if ref_date else date.today())
    ref = end
    start = _parse_date(window_start) if window_start else None
    use_week_window = week_start is not None or week_end is not None or start is None
    selected_week_start: Optional[int] = None
    selected_week_end: Optional[int] = None

    all_sessions_to_ref = [
        s for s in sessions
        if (d := _parse_date(s.get("date", ""))) is not None
        and d <= ref
    ]
    completed_history_to_ref = [
        s for s in all_sessions_to_ref
        if _is_completed_session(s)
    ]

    if use_week_window:
        selected_week_start, selected_week_end = _resolve_week_window(
            sessions,
            current_week,
            weeks,
            program_start,
            week_start=week_start,
            week_end=week_end,
        )
        selected_sessions = _sessions_in_week_window(
            sessions,
            program_start,
            selected_week_start,
            selected_week_end,
        )
        inferred_start, _ = _session_date_bounds(selected_sessions)
        if start is None:
            start = inferred_start or end - timedelta(days=max(7, weeks * 7) - 1)
            window_start = start.isoformat()
        if not window_end:
            window_end = end.isoformat()

        recent_sessions = sorted(
            [
                s for s in selected_sessions
                if (d := _parse_date(s.get("date", ""))) is None or d <= end
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        completed_in_window = sorted(
            [
                s for s in recent_sessions
                if _is_completed_session(s)
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        selected_week_count = max(1, selected_week_end - selected_week_start + 1)
    else:
        cutoff = start
        recent_sessions = sorted(
            [
                s
                for s in all_sessions_to_ref
                if (d := _parse_date(s.get("date", ""))) and d >= cutoff and d <= end
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )

        completed_in_window = sorted(
            [
                s for s in completed_history_to_ref
                if (d := _parse_date(s.get("date", ""))) is not None
                and cutoff <= d <= end
            ],
            key=lambda s: s.get("date", ""),
            reverse=True,
        )
        selected_week_nums = {
            wk for s in completed_in_window
            if (wk := _session_week_num(s, program_start)) is not None
        }
        if selected_week_nums:
            selected_week_start = min(selected_week_nums)
            selected_week_end = max(selected_week_nums)
        selected_week_count = max(1, int(weeks or 1))

    exercise_stats: dict[str, dict[str, Any]] = {}
    for s in completed_in_window:
        for ex in s.get("exercises", []):
            name = ex.get("name", "").strip()
            if not name:
                continue
            kg = _num(ex.get("kg", 0))
            sets = _executed_sets(ex)
            reps = _num(ex.get("reps", 0))
            vol = sets * reps * kg
            if sets <= 0:
                continue
            if name not in exercise_stats:
                exercise_stats[name] = {"total_sets": 0, "total_volume": 0.0, "max_kg": 0.0}
            exercise_stats[name]["total_sets"] += int(sets)
            exercise_stats[name]["total_volume"] += vol
            if kg > exercise_stats[name]["max_kg"]:
                exercise_stats[name]["max_kg"] = kg
    for v in exercise_stats.values():
        v["total_volume"] = round(v["total_volume"], 1)
        v["max_kg"] = round(v["max_kg"], 1)

    sessions_analyzed = len(completed_in_window)

    exercise_names = {ex.get("name", "").lower().strip() for s in completed_in_window for ex in s.get("exercises", []) if ex.get("name") and _executed_sets(ex) > 0}
    tracked_lifts = []
    lift_alias_map = {}
    for canonical, output_key in [("squat", "squat"), ("bench press", "bench"), ("deadlift", "deadlift"), ("bench", "bench")]:
        if canonical in exercise_names and output_key not in lift_alias_map:
            lift_alias_map[output_key] = canonical
            if output_key not in tracked_lifts:
                tracked_lifts.append(output_key)

    lifts_report = {}
    all_flags = []
    for lift_key in tracked_lifts:
        ex_name = lift_alias_map.get(lift_key, lift_key)
        lift_data: dict[str, Any] = {}

        prog = progression_rate(sessions, ex_name, program_start, reference_date=end)
        if "slope_kg_per_week" in prog:
            lift_data["progression_rate_kg_per_week"] = prog["slope_kg_per_week"]
            lift_data["fit_quality"] = prog.get("fit_quality")
            lift_data["kendall_tau"] = prog.get("kendall_tau")
            lift_data["r2"] = prog.get("r2")
            lift_data["r_squared"] = prog.get("r_squared")
        else:
            lift_data["progression_rate_kg_per_week"] = None
            lift_data["fit_quality"] = None
            lift_data["kendall_tau"] = None
            lift_data["r2"] = None
            lift_data["r_squared"] = None

        vol_corr = volume_intensity_correlation(sessions, ex_name, program_start)
        if "volume_series" in vol_corr and len(vol_corr["volume_series"]) >= 2:
            vols = [v[1] for v in vol_corr["volume_series"]]
            intens = [i[1] for i in vol_corr["intensity_series"]]
            prev_vol = vols[-2]
            prev_int = intens[-2]
            lift_data["volume_change_pct"] = round(((vols[-1] - prev_vol) / prev_vol * 100) if prev_vol > 0 else 0, 1)
            lift_data["intensity_change_pct"] = round(((intens[-1] - prev_int) / prev_int * 100) if prev_int > 0 else 0, 1)

        drift = rpe_drift(sessions, ex_name, program_start, phases=phases)
        if "drift_direction" in drift:
            lift_data["rpe_trend"] = drift["drift_direction"]
            if drift.get("flag"):
                all_flags.append(f"{ex_name}_rpe_{drift['flag']}")
        else:
            lift_data["rpe_trend"] = "unknown"

        lift_data["failed_sets"] = int(sum(
            _count_failed_sets(ex)
            for s in completed_in_window
            for ex in s.get("exercises", [])
            if ex.get("name", "").lower().strip() == ex_name
        ))
        lift_data["executed_sets"] = int(sum(
            _executed_sets(ex)
            for s in completed_in_window
            for ex in s.get("exercises", [])
            if ex.get("name", "").lower().strip() == ex_name
        ))
        lift_data["planned_sets"] = int(sum(
            _num(ex.get("sets", 0))
            for s in completed_in_window
            for ex in s.get("exercises", [])
            if ex.get("name", "").lower().strip() == ex_name
        ))
        lift_data["max_kg"] = round(float(max([_num(ex.get("kg", 0)) for s in completed_in_window for ex in s.get("exercises", []) if ex.get("name", "").lower().strip() == ex_name and _executed_sets(ex) > 0] or [0.0])), 1)
        lift_data["total_volume"] = round(float(sum([_executed_volume(ex) for s in completed_in_window for ex in s.get("exercises", []) if ex.get("name", "").lower().strip() == ex_name])), 1)
        lifts_report[ex_name] = lift_data

    comp_maxes_raw = _estimate_maxes_from_comps(program.get("competitions", []), reference_date=ref)
    session_maxes_raw = _estimate_maxes_from_sessions(completed_history_to_ref, reference_date=ref)
    current_maxes_raw = comp_maxes_raw or session_maxes_raw

    target_rpe_mid = None
    if current_phase:
        t_min = current_phase.get("target_rpe_min")
        t_max = current_phase.get("target_rpe_max")
        if t_min is not None and t_max is not None:
            target_rpe_mid = (_num(t_min) + _num(t_max)) / 2.0

    fatigue = fatigue_index(
        completed_history_to_ref,
        days=selected_week_count * 7,
        glossary=glossary,
        current_maxes=current_maxes_raw, 
        program_start=program_start,
        ref_date=ref,
        window_start=window_start,
        window_end=window_end,
        weeks=selected_week_count,
        target_rpe_midpoint=target_rpe_mid
    )
    fatigue_score = fatigue.get("score") if "score" in fatigue else None
    fatigue_components = fatigue.get("components", {}) if "components" in fatigue else {}
    if fatigue.get("flags"):
        all_flags.extend(fatigue["flags"])

    if selected_week_start is not None and selected_week_end is not None:
        compliance_result = session_compliance_for_week_window(
            sessions,
            phases,
            selected_week_start,
            selected_week_end,
            ref_date=ref,
        )
    else:
        compliance_result = session_compliance(sessions, phases, program_start, weeks=selected_week_count, ref_date=ref)
    compliance_obj = {
        "phase": compliance_result.get("phase", "Unknown"),
        "planned": compliance_result.get("planned_sessions", 0),
        "completed": compliance_result.get("completed_sessions", 0),
        "missed": compliance_result.get("missed_sessions", 0),
        "pct": compliance_result.get("compliance_pct", 0),
        "planned_sets": compliance_result.get("planned_sets", 0),
        "completed_sets": compliance_result.get("completed_sets", 0),
        "set_pct": compliance_result.get("set_compliance_pct", 0),
        "planned_reps": compliance_result.get("planned_reps", 0),
        "completed_reps": compliance_result.get("completed_reps", 0),
        "rep_pct": compliance_result.get("rep_compliance_pct", 0),
        "planned_volume": compliance_result.get("planned_volume", 0),
        "completed_volume": compliance_result.get("completed_volume", 0),
        "vol_pct": compliance_result.get("vol_compliance_pct", 0),
    }

    deload_info_raw = _detect_deloads(sessions, program_start)
    deload_info = {
        "deload_weeks": [d["week_num"] for d in deload_info_raw if d["is_deload"]],
        "break_weeks": [d["week_num"] for d in deload_info_raw if d["is_break"]],
        "effective_training_weeks": sum(1 for d in deload_info_raw if d["effective_index"] >= 0),
    }

    maxes_method = "comp_results" if comp_maxes_raw else ("session_estimated" if session_maxes_raw else "none")
    current_maxes_out: dict[str, Any] = {}
    if current_maxes_raw:
        for lk in ("squat", "bench", "deadlift"):
            val = current_maxes_raw.get(lk)
            if val is not None:
                current_maxes_out[lk] = round(_num(val), 1)
    current_maxes_out["method"] = maxes_method

    estimated_dots = None
    estimated_dots_reason = None
    bodyweight = _num(
        meta.get(
            "current_body_weight_kg",
            meta.get("bodyweight_kg", meta.get("body_weight_kg", 0)),
        )
    )
    sex = str(
        meta.get("sex")
        or program.get("settings", {}).get("sex")
        or ""
    ).lower()
    if bodyweight > 0 and sex in ("male", "female") and all(current_maxes_out.get(lk, 0) for lk in ("squat", "bench", "deadlift")):
        total_kg = sum(current_maxes_out.get(lk, 0) for lk in ("squat", "bench", "deadlift"))
        if total_kg > 0:
            estimated_dots = calculate_dots(total_kg, bodyweight, sex)
    else:
        estimated_dots_reason = "Missing sex or bodyweight"

    projections: list[dict[str, Any]] = []
    projection_reason = None
    today = ref
    upcoming = [
        c for c in sorted(program.get("competitions", []), key=lambda x: x.get("date", ""))
        if c.get("status") in ("confirmed", "optional", "completed") and (d := _parse_date(c.get("date", ""))) and d > today
    ]
    to_project = [upcoming[0], upcoming[-1]] if len(upcoming) >= 2 else upcoming[:1]
    projection_calibration = _resolve_projection_lambda_multiplier(program, reference_date=ref)

    for comp in to_project:
        proj = meet_projection(program, sessions, comp_date=comp["date"], ref_date=end)
        if "total" in proj:
            projections.append({
                "total": proj["total"],
                "confidence": proj["confidence"],
                "weeks_to_comp": proj.get("weeks_to_comp"),
                "method": proj.get("method"),
                "comp_name": comp.get("name"),
                "lifts": proj.get("lifts", {}),
                "projection_calibration": proj.get("projection_calibration"),
            })

    if not projections and not to_project and meta.get("comp_date"):
        proj = meet_projection(program, sessions, comp_date=meta["comp_date"], ref_date=end)
        if "total" in proj:
            projections.append({"total": proj["total"], "confidence": proj["confidence"],
                                 "weeks_to_comp": proj.get("weeks_to_comp"), "method": proj.get("method"),
                                 "comp_name": None, "lifts": proj.get("lifts", {}),
                                 "projection_calibration": proj.get("projection_calibration")})
        else:
            projection_reason = proj.get("reason", "Insufficient data for projection")

    attempt_selection = None
    if projections:
        attempt_pct = meta.get("attempt_pct")
        first_proj_lifts = projections[0].get("lifts", {})
        projected_maxes = {
            lift: data.get("projected") for lift, data in first_proj_lifts.items()
            if isinstance(data, dict) and data.get("projected") is not None
        }
        if projected_maxes:
            attempt_selection = compute_attempt_selection(projected_maxes, attempt_pct)

    fatigue_dimensions = None
    banister = None
    monotony_strain = None
    decoupling = None
    taper_quality = None
    if glossary is not None:
        weekly_dim = _weekly_fatigue_by_dimension(completed_in_window, glossary, program_start, current_maxes_raw or {})
        acwr = compute_acwr(
            completed_history_to_ref,
            glossary,
            program_start,
            current_maxes_raw or {},
            phases=phases,
            current_week=current_week,
            ref_date=end,
        )
        spike = _compute_dimensional_spike(weekly_dim)
        weekly_rounded = {wk: {k: round(v, 1) for k, v in dims.items()} for wk, dims in sorted(weekly_dim.items())}
        fatigue_dimensions = {
            "weekly": weekly_rounded,
            "acwr": acwr,
            "spike": spike,
            "dimension_weights": _DIMENSION_WEIGHTS,
            "label": "selected_window_dimensions_current_state_acwr",
        }
        banister = compute_banister_ffm(
            completed_history_to_ref,
            glossary,
            program_start,
            current_maxes_raw or {},
            ref_date=end,
        )
        monotony_strain = compute_monotony_strain(
            completed_history_to_ref,
            glossary,
            program_start,
            current_maxes_raw or {},
            ref_date=end,
        )
        decoupling = compute_decoupling(
            completed_history_to_ref,
            glossary,
            program_start,
            current_maxes_raw or {},
            ref_date=end,
        )
        taper_quality = compute_taper_quality(
            program,
            completed_history_to_ref,
            glossary,
            current_maxes_raw or {},
            program_start,
            ref_date=end,
        )

    inol_result = compute_inol(
        completed_in_window,
        program_start,
        current_maxes_raw,
        program.get("lift_profiles"),
        phases=phases,
        selected_weeks=selected_week_count,
        all_history_sessions=completed_history_to_ref,
        ref_date=end,
    )
    acwr_result = compute_acwr(
        completed_history_to_ref,
        glossary,
        program_start,
        current_maxes_raw,
        phases=phases,
        current_week=current_week,
        ref_date=end,
    )
    ri_result = compute_ri_distribution(completed_in_window, current_maxes_raw)
    specificity_target = _select_specificity_target_competition(program, ref)
    specificity_comp_date = specificity_target.get("date") if specificity_target else None
    specificity_weeks_to_comp = None
    if specificity_comp_date:
        comp_dt = _parse_date(specificity_comp_date)
        if comp_dt is not None and comp_dt > ref:
            specificity_weeks_to_comp = (comp_dt - ref).days / 7.0
    specificity_result = compute_specificity_ratio(
        completed_in_window,
        glossary,
        weeks_to_comp=specificity_weeks_to_comp,
    )
    volume_landmarks = compute_volume_landmarks(
        completed_history_to_ref,
        glossary,
        current_maxes_raw or {},
        program_start,
        ref_date=end,
    )
    readiness_result = compute_readiness_score(all_sessions_to_ref, program, glossary, program_start, reference_date=ref)

    if "flags" in inol_result and inol_result["flags"]:
        all_flags.extend(inol_result["flags"])
    if isinstance(monotony_strain, dict):
        for row in monotony_strain.get("weekly", []):
            for flag in row.get("flags", []):
                if flag not in all_flags:
                    all_flags.append(flag)
    if isinstance(decoupling, dict) and "flags" in decoupling:
        for flag in decoupling["flags"]:
            if flag not in all_flags:
                all_flags.append(flag)

    peaking_timeline = _build_peaking_timeline(
        program,
        sessions,
        glossary,
        ref,
        banister,
        current_maxes_raw or {},
    )
    alerts = generate_alerts(
        {
            "week": current_week,
            "fatigue_index": fatigue_score,
            "current_maxes": current_maxes_out,
            "projections": projections,
            "banister": banister,
            "acwr": acwr_result,
            "decoupling": decoupling,
            "specificity_ratio": specificity_result if "status" not in specificity_result else None,
            "monotony_strain": monotony_strain,
            "readiness_score": readiness_result,
        },
        program,
        completed_history_to_ref,
        glossary,
        ref_date=end,
        window_weeks=selected_week_count,
    )

    return {
        "week": current_week,
        "selected_week_start": selected_week_start,
        "selected_week_end": selected_week_end,
        "selected_week_count": selected_week_count,
        "window_start": window_start,
        "window_end": window_end,
        "selected_session_context": recent_sessions,
        "block": phase_name,
        "lifts": lifts_report,
        "fatigue_index": fatigue_score,
        "fatigue_components": fatigue_components,
        "compliance": compliance_obj,
        "current_maxes": current_maxes_out,
        "estimated_dots": estimated_dots,
        "estimated_dots_reason": estimated_dots_reason,
        "projections": projections,
        "projection_reason": projection_reason,
        "projection_calibration": projection_calibration,
        "flags": all_flags,
        "sessions_analyzed": sessions_analyzed,
        "exercise_stats": exercise_stats,
        "deload_info": deload_info,
        "fatigue_dimensions": fatigue_dimensions,
        "inol": inol_result if "status" not in inol_result else None,
        "acwr": acwr_result,
        "ri_distribution": ri_result if "status" not in ri_result else None,
        "specificity_ratio": specificity_result if "status" not in specificity_result else None,
        "specificity_target_competition": specificity_target,
        "volume_landmarks": volume_landmarks,
        "readiness_score": readiness_result,
        "attempt_selection": attempt_selection,
        "banister": banister,
        "monotony_strain": monotony_strain,
        "decoupling": decoupling,
        "taper_quality": taper_quality,
        "alerts": alerts,
        "peaking_timeline": peaking_timeline,
    }

def _planned_overreach_for_week(phases: list[dict], current_week: int | None, program_start: str = "") -> bool:
    if not phases:
        return False
    wk = current_week if current_week is not None else _calculate_current_week(program_start)
    current_phase = _find_current_phase(phases, wk)
    if not current_phase:
        return False
    intent = str(current_phase.get("intent", "")).lower()
    target_rpe_max = _num(current_phase.get("target_rpe_max"))
    return "overreach" in intent or target_rpe_max >= 9.0

def _competition_qualifying_total(competition: dict) -> float | None:
    if not isinstance(competition, dict):
        return None
    for key in ("qualifying_total_kg", "qualifying_total"):
        value = competition.get(key)
        if value is not None:
            total = _num(value)
            if total > 0:
                return round(total, 1)
    qualifying_totals = competition.get("qualifying_totals")
    if isinstance(qualifying_totals, dict):
        total = _num(qualifying_totals.get("total_kg"))
        if total > 0:
            return round(total, 1)
    return None

def _goal_priority_rank(priority: str | None) -> int:
    order = {"primary": 0, "secondary": 1, "optional": 2}
    return order.get(str(priority or "optional"), 99)

def _competition_goal_qualifying_total(program: dict, competition_date: str) -> float | None:
    candidates: list[tuple[int, float]] = []
    for goal in program.get("goals", []) or []:
        target_dates = [str(value or "").strip() for value in list(goal.get("target_competition_dates") or []) if str(value or "").strip()]
        legacy_target_date = str(goal.get("target_competition_date") or "").strip()
        if legacy_target_date and legacy_target_date not in target_dates:
            target_dates.append(legacy_target_date)
        if competition_date not in target_dates:
            continue
        goal_type = str(goal.get("goal_type") or "")
        target_standard_ids = [str(value or "").strip() for value in list(goal.get("target_standard_ids") or []) if str(value or "").strip()]
        legacy_target_standard_id = str(goal.get("target_standard_id") or "").strip()
        if legacy_target_standard_id and legacy_target_standard_id not in target_standard_ids:
            target_standard_ids.append(legacy_target_standard_id)
        if goal_type != "qualify_for_federation" and not target_standard_ids:
            continue
        total = _num(goal.get("target_total_kg"))
        if total > 0:
            candidates.append((_goal_priority_rank(str(goal.get("priority"))), round(total, 1)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][1]

def _planned_exercise_weight(ex: dict, current_maxes: dict[str, Any]) -> float | None:
    load_type = (
        ex.get("load_type")
        or ex.get("loadSource")
        or ex.get("load_source")
        or ""
    )
    load_type = str(load_type).lower().strip()

    kg = _num(ex.get("kg", ex.get("load_value")))
    if kg > 0 and load_type in ("", "absolute", "kg"):
        return round(float(kg), 3)

    canonical = _canonical_lift_from_name(ex.get("name", ""))
    if canonical is None:
        return None

    current_max = _num(current_maxes.get(canonical))
    if current_max <= 0:
        return None

    pct = ex.get("percent") or ex.get("percentage") or ex.get("pct")
    if pct is None and load_type in ("percent", "percentage", "pct"):
        pct = ex.get("load_value")
    if pct is not None and current_max > 0:
        pct_num = _num(pct)
        if pct_num > 1.5:
            pct_num = pct_num / 100.0
        if 0 < pct_num <= 1.2:
            return round(current_max * pct_num, 3)

    rpe_target = ex.get("rpe_target") or ex.get("rpe")
    if rpe_target is None and load_type == "rpe":
        rpe_target = ex.get("load_value")
    if rpe_target is None:
        if load_type == "unspecified":
            return None
        return None

    try:
        reps = int(_num(ex.get("reps", 0)))
        rpe_int = int(_num(rpe_target))
    except (TypeError, ValueError):
        return None

    if 1 <= reps <= 6 and 6 <= rpe_int <= 10:
        pct_from_table = _RPE_TABLE_PRIMARY.get((reps, rpe_int))
        if pct_from_table is not None:
            return round(current_max * pct_from_table, 3)

    if load_type == "unspecified":
        return None
    return None

def _future_planned_daily_fatigue(
    sessions: list[dict],
    glossary: list[dict] | None,
    current_maxes: dict[str, Any],
    ref_date: date,
    end_day: date,
) -> tuple[dict[date, dict[str, float]], int]:
    daily: dict[date, dict[str, float]] = {}
    unresolved_sets = 0
    for session in sessions:
        d = _parse_date(session.get("date", ""))
        if d is None or d <= ref_date or d > end_day:
            continue
        planned = session.get("planned_exercises") or session.get("exercises") or []
        if not planned:
            continue

        day_dims = daily.setdefault(d, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        for ex in planned:
            if not isinstance(ex, dict):
                continue
            sets = int(_num(ex.get("sets", 0)))
            reps = int(_num(ex.get("reps", 0)))
            if sets <= 0 or reps <= 0:
                continue
            weight = _planned_exercise_weight(ex, current_maxes)
            if weight is None or weight <= 0:
                unresolved_sets += sets
                continue

            profile = _get_fatigue_profile(ex.get("name", ""), glossary)
            canonical = _canonical_lift_from_name(ex.get("name", ""))
            e1rm = _num(current_maxes.get(canonical)) if canonical else 0.0
            rpe = ex.get("rpe_target") or ex.get("rpe")
            if rpe is None and str(ex.get("load_type", "")).lower().strip() == "rpe":
                rpe = ex.get("load_value")
            rpe_num = _num(rpe) if rpe is not None else None
            I = min(1.0, weight / e1rm) if e1rm > 0 else _resolve_intensity(ex.get("name", "").lower(), weight, reps, rpe_num, current_maxes, glossary)
            sf = _per_set_fatigue(weight, reps, profile, I, rpe_num)
            for dim in ("axial", "neural", "peripheral", "systemic"):
                day_dims[dim] += sf[dim] * sets
    return daily, unresolved_sets

def _build_specificity_band_segments(program_start: str, comp_date: date) -> list[dict[str, Any]]:
    start_day = _parse_date(program_start)
    if start_day is None:
        return []

    band_windows = [
        ("16_plus", 16, None),
        ("12_to_16", 12, 16),
        ("8_to_12", 8, 12),
        ("4_to_8", 4, 8),
        ("0_to_4", 0, 4),
    ]
    segments: list[dict[str, Any]] = []
    for label, min_weeks, max_weeks in band_windows:
        band = next(
            (row for row in _SPECIFICITY_BANDS if row["min_weeks"] == min_weeks and row["max_weeks"] == max_weeks),
            None,
        )
        if band is None:
            continue

        seg_start = start_day if max_weeks is None else max(start_day, comp_date - timedelta(weeks=max_weeks))
        seg_end = comp_date if min_weeks == 0 else comp_date - timedelta(weeks=min_weeks)
        if seg_start > seg_end:
            continue
        segments.append(
            {
                "label": label,
                "start_date": seg_start.isoformat(),
                "end_date": seg_end.isoformat(),
                "narrow": band["narrow"],
                "broad": band["broad"],
            }
        )
    return segments

def _build_specificity_timeline(
    sessions: list[dict],
    glossary: list[dict] | None,
    program_start: str,
    comp_date: date,
    ref_date: date,
) -> list[dict[str, Any]]:
    weeks: dict[date, list[dict]] = {}
    start_day = _parse_date(program_start)
    for session in sessions:
        if not (session.get("completed") or session.get("status") in ("logged", "completed")):
            continue
        d = _parse_date(session.get("date", ""))
        if d is None or d > ref_date:
            continue
        week_start = d if start_day is None else _week_start_for_date(d, start_day)
        weeks.setdefault(week_start, []).append(session)

    points: list[dict[str, Any]] = []
    for week_start, week_sessions in sorted(weeks.items()):
        week_end = max((_parse_date(s.get("date", "")) for s in week_sessions), default=None)
        if week_end is None:
            continue
        weeks_to_comp = (comp_date - week_end).days / 7.0
        ratio = compute_specificity_ratio(week_sessions, glossary, weeks_to_comp=weeks_to_comp)
        if "status" in ratio:
            continue
        band = ratio.get("expected_band") or _specificity_expected_band(weeks_to_comp)
        points.append(
            {
                "date": week_end.isoformat(),
                "narrow": ratio["narrow"],
                "broad": ratio["broad"],
                "weeks_to_comp": round(float(weeks_to_comp), 1),
                "expected_band": (
                    {
                        "weeks_to_comp": round(float(weeks_to_comp), 1),
                        "narrow": band["narrow"],
                        "broad": band["broad"],
                    }
                    if band is not None
                    else None
                ),
            }
        )
    return points

def _build_peaking_timeline(
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None,
    ref_date: date,
    banister: dict | None,
    current_maxes: dict[str, Any],
) -> dict[str, Any]:
    meta = program.get("meta", {})
    program_start = meta.get("program_start", "")

    competitions = [
        c
        for c in sorted(program.get("competitions", []), key=lambda x: x.get("date", ""))
        if c.get("status") in ("confirmed", "optional")
        and (comp_dt := _parse_date(c.get("date", ""))) is not None
        and comp_dt > ref_date
    ]

    comp = competitions[0] if competitions else None
    if comp is None and meta.get("comp_date"):
        comp_dt = _parse_date(meta.get("comp_date", ""))
        if comp_dt is not None and comp_dt > ref_date:
            comp = {
                "name": meta.get("program_name") or "Upcoming Meet",
                "date": meta["comp_date"],
                "status": "confirmed",
            }

    if comp is None:
        return {
            "status": "insufficient_data",
            "reason": "No upcoming competition date set",
            "status_color": "gray",
            "status_label": "No upcoming competition",
            "status_message": "Set a competition date to view the peaking timeline.",
            "comp_date": None,
            "current_date": ref_date.isoformat(),
            "current_tsb": None,
            "peak_date": None,
            "peak_delta_days": None,
            "peak_window": {"min": 5, "max": 15},
            "series": [],
            "specificity_points": [],
            "specificity_bands": [],
        }

    comp_date = _parse_date(comp["date"])
    if comp_date is None or comp_date <= ref_date:
        return {
            "status": "insufficient_data",
            "reason": "Competition date is in the past or invalid",
            "status_color": "gray",
            "status_label": "No upcoming competition",
            "status_message": "Set a future competition date to view the peaking timeline.",
            "comp_date": comp.get("date"),
            "current_date": ref_date.isoformat(),
            "current_tsb": None,
            "peak_date": None,
            "peak_delta_days": None,
            "peak_window": {"min": 5, "max": 15},
            "series": [],
            "specificity_points": [],
            "specificity_bands": [],
        }

    if not banister or "series" not in banister or not banister["series"]:
        return {
            "status": "insufficient_data",
            "reason": "No Banister data available",
            "status_color": "gray",
            "status_label": "No Banister data",
            "status_message": "Need Banister data to project the peaking timeline.",
            "comp_date": comp["date"],
            "current_date": ref_date.isoformat(),
            "current_tsb": None,
            "peak_date": None,
            "peak_delta_days": None,
            "peak_window": {"min": 5, "max": 15},
            "series": [],
            "specificity_points": [],
            "specificity_bands": [],
        }

    historical_series = banister["series"]
    historical_map = {
        _parse_date(row.get("date", "")): row
        for row in historical_series
        if isinstance(row, dict) and _parse_date(row.get("date", "")) is not None
    }
    current_row = historical_map.get(ref_date)
    if current_row is None:
        return {
            "status": "insufficient_data",
            "reason": "No Banister point found for the reference date",
            "status_color": "gray",
            "status_label": "No Banister data",
            "status_message": "Need a current Banister point to project the peaking timeline.",
            "comp_date": comp["date"],
            "current_date": ref_date.isoformat(),
            "current_tsb": None,
            "peak_date": None,
            "peak_delta_days": None,
            "peak_window": {"min": 5, "max": 15},
            "series": [],
            "specificity_points": [],
            "specificity_bands": [],
        }

    horizon_end = comp_date + timedelta(days=14)
    future_daily_fatigue, future_unresolved_sets = _future_planned_daily_fatigue(
        sessions,
        glossary,
        current_maxes,
        ref_date,
        horizon_end,
    )

    series: list[dict[str, Any]] = []
    for row in historical_series:
        d = _parse_date(row.get("date", ""))
        if d is None or d > horizon_end:
            continue
        actual_tsb = _num(row.get("tsb")) if d <= ref_date else None
        projected_tsb = _num(row.get("tsb")) if d == ref_date else None
        series.append(
            {
                "date": d.isoformat(),
                "actual_tsb": round(float(actual_tsb), 3) if actual_tsb is not None else None,
                "projected_tsb": round(float(projected_tsb), 3) if projected_tsb is not None else None,
            }
        )

    ctl = _num(current_row.get("ctl"))
    atl = _num(current_row.get("atl"))
    baselines = banister.get("load_baselines") if isinstance(banister, dict) else None
    if not baselines:
        baselines = _banister_dimension_baselines(sessions, glossary, program_start, current_maxes)
    day = ref_date + timedelta(days=1)
    while day <= horizon_end:
        dims = future_daily_fatigue.get(day, {"axial": 0.0, "neural": 0.0, "peripheral": 0.0, "systemic": 0.0})
        load = _normalized_banister_load(dims, baselines)
        ctl = _BANISTER_CTL_LAMBDA * load + (1 - _BANISTER_CTL_LAMBDA) * ctl
        atl = _BANISTER_ATL_LAMBDA * load + (1 - _BANISTER_ATL_LAMBDA) * atl
        tsb = round(float(ctl - atl), 3)
        series.append(
            {
                "date": day.isoformat(),
                "actual_tsb": None,
                "projected_tsb": tsb,
            }
        )
        day += timedelta(days=1)

    peak_date = None
    peak_delta_days = None
    for point in series:
        tsb = point.get("projected_tsb")
        if tsb is None:
            continue
        if 5 <= tsb <= 15:
            peak_date = _parse_date(point["date"])
            if peak_date is not None:
                peak_delta_days = (comp_date - peak_date).days
            break

    projected_points = [
        point for point in series
        if point.get("projected_tsb") is not None
    ]
    closest_point = None
    if projected_points:
        closest_point = min(
            projected_points,
            key=lambda point: abs(float(point["projected_tsb"]) - 10.0),
        )
    closest_peak_date = _parse_date(closest_point["date"]) if closest_point else None
    closest_projected_tsb = float(closest_point["projected_tsb"]) if closest_point else None

    if peak_date is None or peak_delta_days is None:
        status = "significant_deviation"
        status_color = "red"
        status_label = "Significant deviation"
        status_message = "Projected TSB never reaches the peaking window."
    elif abs(peak_delta_days) <= 3:
        status = "on_track"
        status_color = "green"
        status_label = "On track"
        status_message = "On track - peak window lands within ±3 days of comp."
    elif abs(peak_delta_days) <= 10:
        status = "misaligned"
        status_color = "yellow"
        status_label = "Peak misaligned"
        direction = "early" if peak_delta_days > 0 else "late"
        status_message = f"Peak misaligned - currently projected to peak {abs(peak_delta_days)} days {direction}."
    else:
        status = "significant_deviation"
        status_color = "red"
        status_label = "Significant deviation"
        direction = "early" if peak_delta_days > 0 else "late"
        status_message = f"Significant deviation - projected to peak {abs(peak_delta_days)} days {direction}."

    specificity_points = _build_specificity_timeline(sessions, glossary, program_start, comp_date, ref_date)
    specificity_bands = _build_specificity_band_segments(program_start, comp_date)

    return {
        "status": status,
        "status_color": status_color,
        "status_label": status_label,
        "status_message": status_message,
        "comp_date": comp["date"],
        "current_date": ref_date.isoformat(),
        "current_tsb": round(float(current_row.get("tsb", 0.0)), 3),
        "peak_date": peak_date.isoformat() if peak_date else None,
        "peak_delta_days": peak_delta_days,
        "peak_type": "inside_window" if peak_date else "not_reached",
        "closest_peak_date": closest_peak_date.isoformat() if closest_peak_date else None,
        "closest_projected_tsb": round(closest_projected_tsb, 3) if closest_projected_tsb is not None else None,
        "future_unresolved_sets": future_unresolved_sets,
        "peak_window": {"min": 5, "max": 15},
        "series": series,
        "specificity_points": specificity_points,
        "specificity_bands": specificity_bands,
    }

def generate_alerts(
    analysis: dict[str, Any],
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None = None,
    ref_date: date | None = None,
    window_weeks: int = 1,
) -> list[dict[str, Any]]:
    ref = ref_date or date.today()
    program_start = program.get("meta", {}).get("program_start", "")
    phases = program.get("phases", [])
    current_week = _num(analysis.get("week")) if analysis.get("week") is not None else _calculate_current_week(program_start, sessions)
    planned_overreach = _planned_overreach_for_week(phases, int(current_week) if current_week else None, program_start)
    lookback_weeks = max(1, int(window_weeks or 1))

    past_sessions = [
        s for s in sessions
        if (d := _parse_date(s.get("date", ""))) is not None and d <= ref
    ]
    current_maxes = analysis.get("current_maxes") if isinstance(analysis.get("current_maxes"), dict) else _estimate_maxes_from_sessions(past_sessions)

    alerts: list[dict[str, Any]] = []

    fatigue_score = analysis.get("fatigue_index")
    if isinstance(fatigue_score, (int, float)) and fatigue_score >= 0.60:
        lookback_days = max(7, lookback_weeks * 7)
        prev_ref = ref - timedelta(days=7)
        previous = fatigue_index(
            past_sessions,
            days=lookback_days,
            glossary=glossary,
            current_maxes=current_maxes or {},
            program_start=program_start,
            ref_date=prev_ref,
        )
        prev_score = previous.get("score") if isinstance(previous, dict) else None
        if isinstance(prev_score, (int, float)) and fatigue_score > prev_score:
            alerts.append(
                {
                    "severity": "warning",
                    "source": "fatigue",
                    "message": "Fatigue is elevated. Consider a lighter session or deload this week.",
                    "raw_detail": f"fatigue_index={fatigue_score:.3f}, previous_window={prev_score:.3f}, delta={fatigue_score - prev_score:+.3f}",
                }
            )

    acwr = analysis.get("acwr")
    if isinstance(acwr, dict) and acwr.get("status") != "insufficient_data":
        composite = acwr.get("composite")
        if isinstance(composite, (int, float)) and composite > 1.5:
            if planned_overreach:
                alerts.append(
                    {
                        "severity": "info",
                        "source": "acwr",
                        "message": "Load spike is consistent with your planned overreach.",
                        "raw_detail": f"acwr_composite={composite:.3f}, phase_intent=planned overreach",
                    }
                )
            else:
                alerts.append(
                    {
                        "severity": "warning",
                        "source": "acwr",
                        "message": "Training load jumped sharply. Monitor recovery closely.",
                        "raw_detail": f"acwr_composite={composite:.3f}, phase_intent=not overreach",
                    }
                )

    banister = analysis.get("banister")
    if isinstance(banister, dict) and banister.get("status") != "insufficient_data":
        tsb_today = banister.get("tsb_today")
        if isinstance(tsb_today, (int, float)) and tsb_today < -30:
            alerts.append(
                {
                    "severity": "warning",
                    "source": "banister",
                    "message": "You are in deep overload. Performance should rebound after a deload.",
                    "raw_detail": f"tsb_today={tsb_today:.3f}",
                }
            )

        projections = [p for p in analysis.get("projections", []) if isinstance(p, dict)]
        weeks_to_comp = projections[0].get("weeks_to_comp") if projections else None
        if isinstance(tsb_today, (int, float)) and isinstance(weeks_to_comp, (int, float)) and weeks_to_comp <= 2 and 5 <= tsb_today <= 15:
            alerts.append(
                {
                    "severity": "info",
                    "source": "banister",
                    "message": "You're in the peaking window for your upcoming meet.",
                    "raw_detail": f"tsb_today={tsb_today:.3f}, weeks_to_comp={weeks_to_comp:.1f}",
                }
            )

    decoupling = analysis.get("decoupling")
    if isinstance(decoupling, dict) and "flags" in decoupling and "decoupling_fatigue_dominant" in decoupling.get("flags", []):
        series = decoupling.get("series") or []
        latest = series[-1] if series else None
        decoupling_value = _num(latest.get("decoupling")) if latest else 0.0
        e1rm_slope = _num(latest.get("e1rm_slope_pct_per_week")) if latest else 0.0
        fi_slope = _num(latest.get("fi_slope_pct_points_per_week")) if latest else 0.0
        alerts.append(
            {
                "severity": "warning",
                "source": "decoupling",
                "message": "Strength is flat but fatigue is climbing. Accumulated stress is outpacing adaptation.",
                "raw_detail": f"decoupling_fatigue_dominant; current={decoupling_value:.3f}, e1rm_slope={e1rm_slope:.3f}, fi_slope={fi_slope:.3f}" if latest else "decoupling_fatigue_dominant",
            }
        )

    readiness = analysis.get("readiness_score")
    if isinstance(readiness, dict):
        score = readiness.get("score")
        if isinstance(score, (int, float)) and score < 50:
            prev_readiness = compute_readiness_score(past_sessions, program, glossary, program_start, reference_date=ref - timedelta(days=7))
            prev_score = prev_readiness.get("score") if isinstance(prev_readiness, dict) else None
            if isinstance(prev_score, (int, float)) and prev_score < 50:
                alerts.append(
                    {
                        "severity": "warning",
                        "source": "readiness",
                        "message": "Readiness has been low consistently. Check sleep and stress.",
                        "raw_detail": f"readiness={score:.1f}, previous_window={prev_score:.1f}",
                    }
                )

    specificity = analysis.get("specificity_ratio")
    if isinstance(specificity, dict) and "specificity_below_expected" in specificity.get("flags", []):
        expected_band = specificity.get("expected_band") or {}
        expected_narrow = expected_band.get("narrow") or {}
        alerts.append(
            {
                "severity": "caution",
                "source": "specificity",
                "message": "More competition-lift practice recommended given how close your meet is.",
                "raw_detail": (
                    f"narrow={specificity.get('narrow', 0):.3f}, "
                    f"expected_narrow={expected_narrow.get('min', 0):.2f}-{expected_narrow.get('max', 0):.2f}, "
                    f"weeks_to_comp={expected_band.get('weeks_to_comp')}"
                ),
            }
        )

    monotony = analysis.get("monotony_strain")
    if isinstance(monotony, dict):
        weekly = monotony.get("weekly") or []
        latest = weekly[-1] if weekly else None
        if latest and "high_monotony" in latest.get("flags", []):
            alerts.append(
                {
                    "severity": "caution",
                    "source": "monotony",
                    "message": "Your daily training load is very uniform. Consider more contrast between hard and easy days.",
                    "raw_detail": f"week_start={latest.get('week_start')}, monotony={latest.get('monotony'):.3f}, strain={latest.get('strain'):.3f}",
                }
            )

    qualifying_alert: dict[str, Any] | None = None
    projections = [p for p in analysis.get("projections", []) if isinstance(p, dict)]
    upcoming = [
        c
        for c in sorted(program.get("competitions", []), key=lambda x: x.get("date", ""))
        if c.get("status") in ("confirmed", "optional")
        and (comp_dt := _parse_date(c.get("date", ""))) is not None
        and comp_dt > ref
    ]
    projection_by_name = {p.get("comp_name"): p for p in projections if p.get("comp_name")}
    for comp in upcoming:
        qualifying_total = _competition_qualifying_total(comp)
        if qualifying_total is None:
            qualifying_total = _competition_goal_qualifying_total(program, str(comp.get("date") or ""))
        if qualifying_total is None:
            continue
        projection = projection_by_name.get(comp.get("name"))
        if projection is None and projections:
            projection = projections[0]
        if not projection:
            continue
        projected_total = _num(projection.get("total"))
        if projected_total <= 0:
            continue
        weeks_to_comp = _num(projection.get("weeks_to_comp"))
        if projected_total >= qualifying_total:
            qualifying_alert = {
                "severity": "info",
                "source": "projection",
                "message": "You're projected to exceed the qualifying total for this meet.",
                "raw_detail": f"projected_total={projected_total:.1f}, qualifying_total={qualifying_total:.1f}, weeks_to_comp={weeks_to_comp:.1f}",
            }
        elif weeks_to_comp < 6:
            qualifying_alert = {
                "severity": "caution",
                "source": "projection",
                "message": "Your projected total is below the meet's qualifying standard.",
                "raw_detail": f"projected_total={projected_total:.1f}, qualifying_total={qualifying_total:.1f}, weeks_to_comp={weeks_to_comp:.1f}",
            }
        if qualifying_alert:
            break

    if qualifying_alert:
        alerts.append(qualifying_alert)

    severity_order = {"warning": 0, "caution": 1, "info": 2}
    source_order = {
        "fatigue": 0,
        "acwr": 1,
        "decoupling": 2,
        "banister": 3,
        "readiness": 4,
        "specificity": 5,
        "monotony": 6,
        "projection": 7,
    }
    alerts.sort(key=lambda item: (severity_order.get(item.get("severity", "info"), 99), source_order.get(item.get("source", ""), 99)))
    return alerts

def _calculate_current_week(program_start: str, sessions: list[dict] = None) -> int:
    if sessions:
        valid_weeks = []
        today = date.today()
        for s in sessions:
            wn = s.get("week_number")
            if wn is not None:
                status = s.get("status")
                d = _parse_date(s.get("date", ""))
                if s.get("completed") or status in ("logged", "completed") or (d and d <= today):
                    valid_weeks.append(int(wn))
        if valid_weeks:
            return max(valid_weeks)
        all_weeks = [int(s.get("week_number")) for s in sessions if s.get("week_number") is not None]
        if all_weeks:
            return min(all_weeks)

    if not program_start:
        return 1
    try:
        start = datetime.strptime(program_start, "%Y-%m-%d").date()
        days_since = (date.today() - start).days
        return max(1, (days_since // 7) + 1)
    except ValueError:
        return 1

def _find_current_phase(phases: list[dict], current_week: int) -> Optional[dict]:
    for phase in phases:
        if phase.get("start_week", 0) <= current_week <= phase.get("end_week", 0):
            return phase
    return None

def _infer_program_start(sessions: list[dict]) -> str:
    dates = [d for s in sessions if (d := _parse_date(s.get("date", "")))]
    return min(dates).isoformat() if dates else ""
