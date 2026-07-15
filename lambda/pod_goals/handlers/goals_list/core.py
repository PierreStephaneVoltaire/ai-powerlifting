from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    global _store
    if _store is None:
        from _goals_store import GoalsStore as _GS
        _store = _GS(
            table_name=os.environ.get("POWERLIFTING_GOALS_TABLE", "if-powerlifting-goals"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[GoalsTools] GoalsStore initialised from env vars")
    return _store


async def goals_list(args: dict) -> list:
    """List all athlete goals for a user.

    Args:
        args: dict with optional `pk` (defaults to env HEALTH_PROGRAM_PK).
    """
    store = _get_store()
    pk = args.get("pk") if isinstance(args, dict) else None
    if pk:
        store.pk = pk
    return await store.list_goals(pk or os.environ.get("HEALTH_PROGRAM_PK", "operator"))
