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


def _store_for(pk: str | None):
    """Return the ProgramStore singleton, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


async def health_get_meta(args: dict | None = None) -> dict:
    """Get program metadata without the full program.

    Returns:
        Dict with comp_date, program_start, targets, version, weight_class,
        training_notes, change_log, and other meta fields.
    """
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    program = await store.get_program()
    return program.get("meta", {})