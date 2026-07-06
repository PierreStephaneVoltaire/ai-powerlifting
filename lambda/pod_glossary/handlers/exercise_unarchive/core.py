from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_glossary_store: Optional[Any] = None


def _get_glossary_store():
    global _glossary_store
    if _glossary_store is None:
        from glossary_store import GlossaryStore as _GS
        _glossary_store = _GS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[ExerciseTools] GlossaryStore initialised from env vars")
    return _glossary_store


async def exercise_unarchive(args: dict) -> dict:
    """Unarchive an exercise by id (sets archived=false).

    Args:
        args: dict with optional `pk`, and required `id` (exercise id).
    """
    store = _get_glossary_store()
    if args.get("pk"):
        store.pk = args["pk"]
    exercise_id = args.get("id") or ""
    await store.set_archived(exercise_id, False)
    return {"status": "unarchived", "id": exercise_id}