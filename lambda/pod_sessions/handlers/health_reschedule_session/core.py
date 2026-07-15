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


async def health_reschedule_session(args: dict | None = None, old_date: str | None = None, new_date: str | None = None) -> dict:
    """Move a session to a different date.

    Args:
        old_date: Current session date (YYYY-MM-DD)
        new_date: Target date (YYYY-MM-DD)

    Returns:
        The updated session dict

    Raises:
        ValueError: If old session not found or new date already occupied
    """
    if isinstance(args, dict):
        if old_date is None:
            old_date = args.get("old_date")
        if new_date is None:
            new_date = args.get("new_date")
    pk = args.get("pk") if isinstance(args, dict) else None
    datetime.strptime(old_date, "%Y-%m-%d")
    datetime.strptime(new_date, "%Y-%m-%d")

    store = _store_for(pk)
    program = await store.get_program()
    table, active_pk, _ = _get_table_and_pk()
    program_sk = _resolve_program_sk(table, active_pk, "current")
    from session_store import SessionStore
    session_store = SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    )
    if await session_store.get_sessions_range(program_sk, new_date, new_date, program.get("phases", [])):
        raise ValueError(f"A session already exists on {new_date}")
    updated = await session_store.patch_session(
        program_sk,
        old_date,
        {"date": new_date},
        program.get("phases", []),
    )
    store.invalidate_cache()
    return updated