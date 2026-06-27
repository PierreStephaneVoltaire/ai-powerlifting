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


async def health_get_competition(date: str) -> dict:
    """Load a specific competition by date.

    Args:
        date: Competition date (YYYY-MM-DD)

    Returns:
        Full competition object including targets, between_comp_plan, comp_day_protocol

    Raises:
        ValueError: If competition not found
        ProgramNotFoundError: If no program exists
    """
    store = _get_store()
    program = await store.get_program()

    competitions = program.get("competitions", [])
    for comp in competitions:
        if comp.get("date") == date:
            return comp

    raise ValueError(f"Competition not found with date={date}")