from __future__ import annotations

import logging
import os
from datetime import datetime
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


def _store_for(pk: str | None):
    """Return the ProgramStore singleton, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


def _resolve_program_sk(table, pk: str, version: str) -> str:
    if version == "current":
        pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


async def health_create_session(
    args: dict | None = None,
    date: str | None = None,
    day: str | None = None,
    week_number: int | None = None,
    exercises: list[dict] | None = None,
    session_notes: str = "",
) -> dict:
    """Create a new training session.

    Args:
        date: Session date (YYYY-MM-DD)
        day: Day label e.g. "Monday"
        week_number: Training week number (integer)
        exercises: Optional list of exercise dicts {name, sets, reps, kg, rpe, notes}
        session_notes: Optional session notes

    Returns:
        The created session dict

    Raises:
        ValueError: If session already exists on that date
    """
    if isinstance(args, dict):
        if date is None:
            date = args.get("date")
        if day is None:
            day = args.get("day")
        if week_number is None:
            week_number = args.get("week_number")
        if exercises is None:
            exercises = args.get("exercises")
        if not session_notes:
            session_notes = args.get("session_notes", "")
    pk = args.get("pk") if isinstance(args, dict) else None
    datetime.strptime(date, "%Y-%m-%d")

    store = _store_for(pk)
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    new_session = {
        "date": date,
        "day": day,
        "week": f"W{week_number}",
        "week_number": week_number,
        "block": "current",
        "status": "planned",
        "completed": False,
        "session_rpe": None,
        "body_weight_kg": None,
        "session_notes": session_notes,
        "planned_exercises": [],
        "exercises": exercises or [],
    }
    from session_store import SessionStore
    created = await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).create_session(program_sk, new_session, program.get("phases", []))
    store.invalidate_cache()
    return created