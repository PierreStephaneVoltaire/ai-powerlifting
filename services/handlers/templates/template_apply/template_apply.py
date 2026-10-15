
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Literal, List

from .training_weeks import WEEKDAY_INDEX, normalize_week_start_day, week_start_date

def round_to_2_5(kg: float) -> float:
    """Round a weight to the nearest 2.5kg (standard plate increment)."""
    return round(kg / 2.5) * 2.5

def check_max_resolution_gate(
    template: dict[str, Any], 
    current_maxes: dict[str, float], 
    glossary_exercises: list[dict[str, Any]]
) -> list[str]:

    required_ids = template.get("required_maxes", [])
    missing = []
    
    glossary_map = {ex["id"]: ex for ex in glossary_exercises}
    
    for gid in required_ids:
        if gid in ["squat", "bench", "deadlift"]:
            if gid not in current_maxes or not current_maxes[gid]:
                missing.append(gid)
            continue
            
        ex = glossary_map.get(gid)
        if not ex:
            missing.append(gid)
            continue
            
        if not ex.get("e1rm_estimate"):
            missing.append(gid)
            
    return missing

def _get_e1rm(gid: str, current_maxes: dict[str, float], glossary_map: dict[str, dict]) -> float | None:
    if gid in current_maxes:
        return current_maxes[gid]
    ex = glossary_map.get(gid)
    if ex and ex.get("e1rm_estimate"):
        return ex["e1rm_estimate"].get("value_kg")
    return None

def rpe_to_percent(reps: int | float | None, rpe: int | float | None) -> float | None:
    """Estimate %1RM from reps and RPE using a simple Epley-style rule."""
    try:
        reps_value = float(reps)
        rpe_value = float(rpe)
    except (TypeError, ValueError):
        return None
    if reps_value <= 0 or rpe_value <= 0:
        return None
    effective_reps = reps_value + max(0.0, 10.0 - rpe_value)
    return 1.0 / (1.0 + effective_reps / 30.0)

def concretize(
    template: dict[str, Any],
    current_maxes: dict[str, float],
    glossary_exercises: list[dict[str, Any]],
    start_date: date,
    week_start_day: str = "Monday",
) -> list[dict[str, Any]]:
    """Map template sessions to calendar dates and resolve loads."""
    glossary_map = {ex["id"]: ex for ex in glossary_exercises}
    resolved_week_start_day = normalize_week_start_day(week_start_day)
    anchor = week_start_date(start_date, 1, resolved_week_start_day)

    sessions = template.get("sessions", [])
    if not sessions:
        return []

    def day_offset(tpl_sess: dict[str, Any]) -> int:
        day_name = tpl_sess.get("day_of_week")
        if isinstance(day_name, str) and day_name in WEEKDAY_INDEX:
            return (WEEKDAY_INDEX[day_name] - WEEKDAY_INDEX[resolved_week_start_day]) % 7
        raw_idx = tpl_sess.get("day_index", 0)
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            return 0
        return idx - 1 if 1 <= idx <= 7 else max(0, min(6, idx))

    concrete_sessions = []
    
    for tpl_sess in sessions:
        week_number = int(tpl_sess.get("week_number") or 1)
        sess_date = anchor + timedelta(weeks=week_number - 1, days=day_offset(tpl_sess))
        if sess_date < start_date:
            continue
        
        exercises = []
        for tpl_ex in tpl_sess.get("exercises", []):
            gid = tpl_ex.get("glossary_id")
            load_type = tpl_ex.get("load_type", "unresolvable")
            load_value = tpl_ex.get("load_value")
            rpe_target = tpl_ex.get("rpe_target")
            
            kg = None
            load_source = load_type
            
            if load_type == "percentage" and load_value:
                e1rm = _get_e1rm(gid, current_maxes, glossary_map)
                if e1rm:
                    kg = round_to_2_5(e1rm * load_value)
                else:
                    load_source = "unresolvable"
            elif load_type == "absolute":
                kg = load_value
            elif load_type == "rpe":
                e1rm = _get_e1rm(gid, current_maxes, glossary_map)
                pct = rpe_to_percent(tpl_ex.get("reps"), rpe_target)
                if e1rm and pct:
                    kg = round_to_2_5(e1rm * pct)
                    load_source = "rpe_estimate"
                else:
                    load_source = "unresolvable"
                
            exercises.append({
                "name": tpl_ex["name"],
                "glossary_id": gid,
                "sets": tpl_ex.get("sets"),
                "reps": tpl_ex.get("reps"),
                "kg": kg,
                "rpe_target": rpe_target,
                "load_source": load_source,
                "notes": tpl_ex.get("notes", "")
            })
            
        concrete_sessions.append({
            "date": sess_date.isoformat(),
            "day": sess_date.strftime("%A"),
            "week": tpl_sess.get("label", f"W{week_number}"),
            "week_number": week_number,
            "status": "planned",
            "completed": False,
            "planned_exercises": exercises,
            "exercises": [],
            "session_notes": ""
        })
        
    return concrete_sessions
