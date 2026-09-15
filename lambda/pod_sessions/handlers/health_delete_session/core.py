from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional
from session_store import require_mutation_envelope

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
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


async def health_delete_session(args: dict | str | None = None, date: str | None = None) -> dict:
    """Delete a training session by date.

    Args:
        date: Session date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If session not found
    """
    if date is None:
        date = args.get("date") if isinstance(args, dict) else args
    pk = args.get("pk") if isinstance(args, dict) else None
    session_id = args.get("session_id") if isinstance(args, dict) else None
    expected_revision, idempotency_key = require_mutation_envelope(
        args.get("expected_revision") if isinstance(args, dict) else None,
        args.get("idempotency_key") if isinstance(args, dict) else None,
    )
    store = _store_for(pk)
    program = await store.get_program()
    table, active_pk = store.table, store.pk
    program_sk = _resolve_program_sk(table, active_pk, "current")
    from session_store import SessionStore
    result = await SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=active_pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    ).delete_session(
        program_sk,
        date,
        None,
        expected_revision,
        idempotency_key,
        session_id,
    )
    store.invalidate_cache()
    return result
