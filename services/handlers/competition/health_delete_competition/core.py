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


async def health_delete_competition(args: dict | str | None = None, date: str | None = None) -> dict:
    """Delete a competition by date.

    Args:
        date: Competition date (YYYY-MM-DD)

    Returns:
        {"deleted": date}

    Raises:
        ValueError: If competition not found
    """
    import copy
    if date is None:
        date = args.get("date") if isinstance(args, dict) else args
    if not isinstance(date, str):
        raise ValueError("date is required")
    pk = args.get("pk") if isinstance(args, dict) else None
    expected_revision = args.get("expected_revision") if isinstance(args, dict) else None
    idempotency_key = args.get("idempotency_key") if isinstance(args, dict) else None
    store = _store_for(pk)

    def mutate(program: dict) -> dict:
        competitions = program.get("competitions", [])
        before = len(competitions)
        program["competitions"] = [c for c in competitions if c.get("date") != date]
        if len(program["competitions"]) == before:
            raise ValueError(f"Competition not found: {date}")
        return {"deleted": date}

    return await store.mutate_source(
        "competition_delete",
        {"date": date},
        expected_revision,
        idempotency_key,
        mutate,
    )
