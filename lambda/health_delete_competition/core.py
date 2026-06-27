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


async def health_delete_competition(date: str) -> dict:
    """Delete a competition by date.

    Args:
        date: Competition date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If competition not found
    """
    import copy
    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    competitions = new_program.get("competitions", [])
    before = len(competitions)
    new_program["competitions"] = [c for c in competitions if c.get("date") != date]

    if len(new_program["competitions"]) == before:
        raise ValueError(f"Competition not found: {date}")

    await store._write_new_version(new_program, minor=True)
    return {"deleted": date}