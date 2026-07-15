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


async def health_delete_diet_note(args: dict | str | None = None, date: str | None = None) -> dict:
    """Delete a diet note by date.

    Args:
        date: Diet note date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If diet note not found
    """
    import copy
    if date is None:
        date = args.get("date") if isinstance(args, dict) else args
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    notes = new_program.get("diet_notes", [])
    before = len(notes)
    new_program["diet_notes"] = [n for n in notes if n.get("date") != date]

    if len(new_program["diet_notes"]) == before:
        raise ValueError(f"Diet note not found: {date}")

    await store._write_new_version(new_program, minor=True)
    return {"deleted": date}