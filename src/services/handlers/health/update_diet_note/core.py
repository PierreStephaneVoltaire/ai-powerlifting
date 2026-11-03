from __future__ import annotations
import logging
from typing import Optional
logger = logging.getLogger(__name__)
_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]
def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    import os
    from services.lib.program_store import ProgramStore as _PS
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


async def health_update_diet_note(args: dict | None = None, date: str | None = None, notes: str | None = None) -> dict:
    """Update or create a diet note for a specific date.

    Creates a new minor version of the program. Replaces existing content.

    Args:
        date: Date for the diet note (YYYY-MM-DD)
        notes: The diet notes content

    Returns:
        Updated diet note object {date, notes}
    """

    if isinstance(args, dict):
        if date is None:
            date = args.get("date")
        if notes is None:
            notes = args.get("notes")
    pk = args.get("pk") if isinstance(args, dict) else None

    store = _store_for(pk)
    return await store.upsert_diet_note(date, notes, args.get("expected_revision"), args.get("idempotency_key"))
