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


async def health_update_phases(args: dict | None = None, phases: list[dict] | None = None) -> list[dict]:
    """Replace the full phases array.

    Each phase dict: name (required), start_week (int), end_week (int), intent (str).

    Args:
        phases: Complete list of phase dicts

    Returns:
        The updated phases list

    Raises:
        ValueError: If any phase is missing required fields
    """
    if phases is None:
        phases = args.get("phases") if isinstance(args, dict) else None
    pk = args.get("pk") if isinstance(args, dict) else None
    for i, phase in enumerate(phases):
        if not phase.get("name"):
            raise ValueError(f"phases[{i}].name is required")

    store = _store_for(pk)
    return await store.update_phases(phases, None, args.get("expected_revision"), args.get("idempotency_key"))
