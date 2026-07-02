from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    global _store
    if _store is None:
        from goals_store import GoalsStore as _GS
        _store = _GS(
            table_name=os.environ.get("POWERLIFTING_GOALS_TABLE", "if-powerlifting-goals"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[GoalsTools] GoalsStore initialised from env vars")
    return _store


async def goals_replace(args: dict) -> dict:
    """Full replace of a user's athlete goals (upsert incoming by id, delete missing).

    Args:
        args: dict with optional `pk` and required `goals` (array of raw goal bodies).
    """
    store = _get_store()
    pk = args.get("pk") if isinstance(args, dict) else None
    if pk:
        store.pk = pk
    goals = args.get("goals") if isinstance(args, dict) else None
    if not isinstance(goals, list):
        raise ValueError("goals must be an array")
    await store.replace_goals(pk or os.environ.get("HEALTH_PROGRAM_PK", "operator"), goals)
    return {"success": True}
