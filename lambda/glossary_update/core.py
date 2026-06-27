from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_glossary_store: Optional[Any] = None


def _get_glossary_store():
    """Lazily create and return the GlossaryStore singleton."""
    global _glossary_store
    if _glossary_store is None:
        import os
        from glossary_store import GlossaryStore as _GS
        _glossary_store = _GS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] GlossaryStore initialised from env vars")
    return _glossary_store


async def glossary_update(exercise_id: str, fields: dict) -> dict:
    glossary_store = _get_glossary_store()
    if "tertiary_muscles" in fields and fields["tertiary_muscles"] is None:
        fields["tertiary_muscles"] = []
    await glossary_store.update_exercise(exercise_id, fields)
    return {"status": "updated", "id": exercise_id}