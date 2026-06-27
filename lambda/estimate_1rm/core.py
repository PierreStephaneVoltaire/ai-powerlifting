from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional


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


_CONSERVATIVE_REP_PCT: dict[int, float] = {
    1: 1.000,
    2: 0.955,
    3: 0.925,
    4: 0.898,
    5: 0.875,
}


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