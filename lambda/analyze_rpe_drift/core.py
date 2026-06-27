"""Lambda core for analyze_rpe_drift — replicates tools/health/tool.py dispatcher.

Loads program+sessions via the ProgramStore layer (same as
_get_program_and_sessions in tool.py), then calls analytics.rpe_drift
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


# ---- analytics.py verbatim helpers (rpe_drift deps) ----

INSUFFICIENT_DATA = {"status": "insufficient_data"}


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


# ---- dispatcher (replicates tool.py _do_analyze_rpe_drift + _get_program_and_sessions) ----

async def analyze_rpe_drift(args: dict) -> dict:
    """Load program+sessions from store, then call analytics.rpe_drift.

    Replicates tool.py:
        program, sessions, program_start = _get_program_and_sessions()
        return rpe_drift(sessions, args["exercise_name"], program_start, args.get("window_weeks", 4))
    """
    store = _get_store()
    program = await store.get_program()
    sessions = program.get("sessions", [])
    program_start = program.get("meta", {}).get("program_start", "")
    phases = program.get("phases", [])
    return rpe_drift(
        sessions,
        args["exercise_name"],
        program_start,
        args.get("window_weeks", 4),
        phases,
    )