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


async def health_update_diet_note(args: dict | None = None, date: str | None = None, notes: str | None = None) -> dict:
    """Update or create a diet note for a specific date.

    Creates a new minor version of the program. Replaces existing content.

    Args:
        date: Date for the diet note (YYYY-MM-DD)
        notes: The diet notes content

    Returns:
        Updated diet note object {date, notes}
    """
    import copy

    if isinstance(args, dict):
        if date is None:
            date = args.get("date")
        if notes is None:
            notes = args.get("notes")
    pk = args.get("pk") if isinstance(args, dict) else None

    store = _store_for(pk)
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    diet_notes = new_program.get("diet_notes", [])

    note_idx = None
    for i, note in enumerate(diet_notes):
        if note.get("date") == date:
            note_idx = i
            break

    new_note = {"date": date, "notes": notes}

    if note_idx is not None:
        diet_notes[note_idx] = new_note
    else:
        diet_notes.append(new_note)

    new_program["diet_notes"] = diet_notes

    await store._write_new_version(new_program, minor=True)

    return new_note