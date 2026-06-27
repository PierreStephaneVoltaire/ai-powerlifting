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


async def health_update_phases(phases: list[dict]) -> list[dict]:
    """Replace the full phases array.

    Each phase dict: name (required), start_week (int), end_week (int), intent (str).

    Args:
        phases: Complete list of phase dicts

    Returns:
        The updated phases list

    Raises:
        ValueError: If any phase is missing required fields
    """
    import copy
    for i, phase in enumerate(phases):
        if not phase.get("name"):
            raise ValueError(f"phases[{i}].name is required")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)
    new_program["phases"] = phases

    await store._write_new_version(new_program, minor=True)
    return phases