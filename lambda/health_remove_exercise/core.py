from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _get_table_and_pk():
    store = _get_store()
    return store.table, store.pk, store


def _resolve_program_sk(table, pk: str, version: str) -> str:
    if version == "current":
        pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


def _resolve_phase(session: dict, phases: list[dict]) -> dict:
    """Resolve the phase object for a session based on week_number.

    Args:
        session: Session dict with week_number
        phases: List of phase dicts from program

    Returns:
        Matching phase dict, or first phase if no match
    """
    week_number = session.get("week_number", 1)
    for phase in phases:
        start = phase.get("start_week", 0)
        end = phase.get("end_week", 99)
        if start <= week_number <= end:
            return phase
    return phases[0] if phases else {}


async def health_get_session(date: str) -> dict:
    """Load a single session by date.

    Args:
        date: Session date (YYYY-MM-DD)

    Returns:
        Session object with exercises and resolved phase object

    Raises:
        ValueError: If session not found
    """
    store = _get_store()
    program = await store.get_program()

    phases = program.get("phases", [])
    sessions = program.get("sessions", [])

    for session in sessions:
        if session.get("date") == date:
            session_copy = dict(session)
            session_copy["phase"] = _resolve_phase(session, phases)
            return session_copy

    raise ValueError(f"Session not found with date={date}")


async def health_remove_exercise(date: str, exercise_index: int) -> dict:
    """Remove an exercise from a session by index.

    Args:
        date: Session date (YYYY-MM-DD)
        exercise_index: Zero-based index of the exercise to remove

    Returns:
        The updated session exercises list

    Raises:
        ValueError: If session not found or index out of range
    """
    store = _get_store()
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    session = await health_get_session(date)
    exercises = list(session.get("exercises") or [])
    if exercise_index < 0 or exercise_index >= len(exercises):
        raise ValueError(f"Exercise index {exercise_index} out of range (0-{len(exercises)-1})")

    exercises.pop(exercise_index)

    from session_store import SessionStore
    await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).patch_session(program_sk, date, {"exercises": exercises}, program.get("phases", []))
    store.invalidate_cache()
    return {"date": date, "exercises": exercises}