from __future__ import annotations

import logging
from datetime import datetime
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


async def health_update_session(date_str: str, patch: dict) -> dict:
    """Update a session by date with the given patch.

    Validates date format and patch keys before applying.

    Args:
        date_str: ISO8601 date string (YYYY-MM-DD)
        patch: Dict with session fields to update

    Allowed patch keys:
        - completed: bool
        - session_rpe: float
        - body_weight_kg: float
        - session_notes: str
        - exercises: list

    Returns:
        Updated session dict (not full program)

    Raises:
        ValueError: If date format invalid, patch keys invalid, or session not found
        RuntimeError: If store not initialized or DynamoDB fails
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.")

    allowed_keys = {"completed", "session_rpe", "body_weight_kg", "session_notes", "exercises"}
    unknown_keys = set(patch.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(f"Unknown patch keys: {unknown_keys}. Allowed: {allowed_keys}")

    store = _get_store()
    updated_program = await store.update_session(date_str, patch)
    if patch.get("completed") is True:
        try:
            from cache_invalidation import mark_markdown_export_dirty
            mark_markdown_export_dirty(
                store.pk,
                getattr(store, "_table_name", None),
                getattr(store, "_region", None),
                reason="session_completion",
            )
        except Exception as exc:
            logger.warning("[HealthTools] Markdown export dirty marker failed: %s", exc)

    sessions = updated_program.get("sessions", [])
    for session in sessions:
        if session.get("date") == date_str:
            return session

    raise RuntimeError(f"Session update succeeded but session not found: {date_str}")