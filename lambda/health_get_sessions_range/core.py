from __future__ import annotations

import logging
from typing import Optional

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


async def health_get_sessions_range(start_date: str, end_date: str) -> list[dict]:
    """Load sessions within a date range.

    Args:
        start_date: Start of range (YYYY-MM-DD)
        end_date: End of range (YYYY-MM-DD)

    Returns:
        Array of sessions in date order, each with resolved phase object
    """
    store = _get_store()
    program = await store.get_program()

    phases = program.get("phases", [])
    sessions = program.get("sessions", [])

    result = []
    for session in sessions:
        session_date = session.get("date", "")
        if start_date <= session_date <= end_date:
            session_copy = dict(session)
            session_copy["phase"] = _resolve_phase(session, phases)
            result.append(session_copy)

    result.sort(key=lambda x: x.get("date", ""))
    return result