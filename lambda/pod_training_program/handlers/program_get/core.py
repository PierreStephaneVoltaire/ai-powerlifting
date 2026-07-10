from __future__ import annotations
import asyncio
from decimal import Decimal
from program_tool_helpers import get_store


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        if isinstance(value, Decimal):
            return float(value) if value % 1 != 0 else int(value)
        f = float(value)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return None


def _coerce_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 != 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _coerce_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_decimals(v) for v in obj]
    return obj


# Numeric fields on planned/logged exercises that must always be numbers.
# Legacy data sometimes stores these as strings (e.g. "5" instead of 5).
_EXERCISE_NUMERIC_FIELDS = ("sets", "reps", "kg", "rpe_target", "session_rpe", "body_weight_kg")


def _normalize_exercise_numerics(exercise: dict) -> dict:
    """Coerce string-typed numeric fields on a planned/logged exercise to numbers."""
    for field in _EXERCISE_NUMERIC_FIELDS:
        if field in exercise:
            exercise[field] = _to_number(exercise[field])
    return exercise


def _normalize_session_numerics(program: dict) -> dict:
    """Normalize numeric fields on all planned_exercises and exercises in sessions."""
    sessions = program.get("sessions")
    if not isinstance(sessions, list):
        return program
    for session in sessions:
        if not isinstance(session, dict):
            continue
        if isinstance(session.get("body_weight_kg"), (str, Decimal)):
            session["body_weight_kg"] = _to_number(session.get("body_weight_kg"))
        if isinstance(session.get("session_rpe"), (str, Decimal)):
            session["session_rpe"] = _to_number(session.get("session_rpe"))
        for key in ("planned_exercises", "exercises"):
            exercises = session.get(key)
            if isinstance(exercises, list):
                session[key] = [
                    _normalize_exercise_numerics(ex) if isinstance(ex, dict) else ex
                    for ex in exercises
                ]
    return program


def _coerce_current_maxes(program: dict) -> dict:
    maxes = program.get("current_maxes")
    if isinstance(maxes, dict):
        program["current_maxes"] = {k: _to_number(v) for k, v in maxes.items()}
    return program


async def program_get(args: dict):
    store = get_store(args)
    program = await store.get_program()
    program_sk = await asyncio.get_running_loop().run_in_executor(
        None, store._current_program_sk_sync
    )
    program["sessions"] = await store._get_session_store().list_sessions(
        str(program_sk),
        program.get("phases", []) if isinstance(program.get("phases"), list) else [],
    )
    program = _coerce_decimals(program)
    program = _normalize_session_numerics(program)
    return program
