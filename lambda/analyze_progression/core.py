"""Lambda core for analyze_progression — replicates tools/health/tool.py dispatcher.

Loads program+sessions via the ProgramStore layer (same as
_get_program_and_sessions in tool.py), then calls analytics.progression_rate
verbatim from tools/health/analytics.py.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Optional

from scipy.stats import kendalltau, theilslopes

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


# ---- analytics.py verbatim helpers (progression_rate deps) ----

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


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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


def _infer_program_start(sessions: list[dict]) -> str:
    dates = [d for s in sessions if (d := _parse_date(s.get("date", "")))]
    return min(dates).isoformat() if dates else ""
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