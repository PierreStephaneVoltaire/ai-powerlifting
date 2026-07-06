from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_glossary_store: Optional[Any] = None


def _get_glossary_store():
    """Lazily create and return the GlossaryStore singleton."""
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


async def exercise_get_glossary(args: dict) -> dict:
    """Get the full exercise glossary (pk, sk, exercises, updated_at).

    Args:
        args: dict with optional `pk` (overrides env HEALTH_PROGRAM_PK).
    """
    store = _get_glossary_store()
    if args.get("pk"):
        store.pk = args["pk"]
    glossary = await store.get_full_store()
    return glossary