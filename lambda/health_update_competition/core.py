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


async def health_update_competition(date: str, patch: dict) -> dict:
    """Update a competition by date.

    Creates a new minor version of the program.

    Args:
        date: Competition date to update
        patch: Fields to update (targets, status, notes, between_comp_plan, etc.)

    Returns:
        Updated competition object

    Raises:
        ValueError: If competition not found
    """
    import copy

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    competitions = new_program.get("competitions", [])
    comp_idx = None
    for i, comp in enumerate(competitions):
        if comp.get("date") == date:
            comp_idx = i
            break

    if comp_idx is None:
        raise ValueError(f"Competition not found with date={date}")

    for key, value in patch.items():
        competitions[comp_idx][key] = value

    await store._write_new_version(new_program, minor=True)

    return competitions[comp_idx]