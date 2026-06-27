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


async def health_get_program() -> dict:
    """Get the full training program.

    Returns:
        Full program dict from cache or DynamoDB

    Raises:
        ProgramNotFoundError: If no program exists
        RuntimeError: If store not initialized or DynamoDB fails
    """
    store = _get_store()
    return await store.get_program()