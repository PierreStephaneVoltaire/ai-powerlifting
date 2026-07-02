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


async def health_update_supplements(args: dict | None = None, patch: dict | None = None) -> dict:
    """Update supplements or supplement phases.

    Creates a new minor version of the program.

    Args:
        patch: {"supplements": [...]} or {"supplement_phases": [...]} or both

    Returns:
        Updated {supplements: [...], supplement_phases: [...]}
    """
    import copy

    if patch is None:
        patch = args.get("patch") if isinstance(args, dict) else None
    pk = args.get("pk") if isinstance(args, dict) else None

    store = _store_for(pk)
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    if "supplements" in patch:
        new_program["supplements"] = patch["supplements"]

    if "supplement_phases" in patch:
        new_program["supplement_phases"] = patch["supplement_phases"]

    await store._write_new_version(new_program, minor=True)

    return {
        "supplements": new_program.get("supplements", []),
        "supplement_phases": new_program.get("supplement_phases", []),
    }