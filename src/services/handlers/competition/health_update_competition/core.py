from __future__ import annotations
import logging
from typing import Optional
from services.lib.block_scope import stamp
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


async def health_update_competition(args: dict | None = None, date: str | None = None, patch: dict | None = None) -> dict:
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

    if isinstance(args, dict):
        if date is None:
            date = args.get("date")
        if patch is None:
            patch = args.get("patch")
    pk = args.get("pk") if isinstance(args, dict) else None
    expected_revision = args.get("expected_revision") if isinstance(args, dict) else None
    idempotency_key = args.get("idempotency_key") if isinstance(args, dict) else None
    if not isinstance(date, str):
        raise ValueError("date is required")
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")

    store = _store_for(pk)

    def mutate(program: dict) -> dict:
        competitions = program.get("competitions", [])
        for comp in competitions:
            if comp.get("date") == date:
                stamp(comp, program, field="competitions")
                comp.update(copy.deepcopy(patch))
                return copy.deepcopy(comp)
        raise ValueError(f"Competition not found with date={date}")

    return await store.mutate_source(
        "competition_update",
        {"date": date, "patch": copy.deepcopy(patch)},
        expected_revision,
        idempotency_key,
        mutate,
    )
