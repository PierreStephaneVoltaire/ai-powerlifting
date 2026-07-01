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


async def health_get_diet_notes(
    args: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Get diet notes, optionally filtered by date range.

    Args:
        start_date: Optional start of range (YYYY-MM-DD)
        end_date: Optional end of range (YYYY-MM-DD)

    Returns:
        Array of {date, notes} sorted by date descending
    """
    if isinstance(args, dict):
        if start_date is None:
            start_date = args.get("start_date")
        if end_date is None:
            end_date = args.get("end_date")
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    program = await store.get_program()

    diet_notes = program.get("diet_notes", [])

    if start_date or end_date:
        filtered = []
        for note in diet_notes:
            note_date = note.get("date", "")
            if start_date and note_date < start_date:
                continue
            if end_date and note_date > end_date:
                continue
            filtered.append(note)
        diet_notes = filtered

    diet_notes.sort(key=lambda x: x.get("date", ""), reverse=True)
    return diet_notes