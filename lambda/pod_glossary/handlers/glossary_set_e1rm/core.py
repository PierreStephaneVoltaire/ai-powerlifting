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


async def glossary_set_e1rm(exercise_id: str, value_kg: float, method: str = "manual") -> dict:
    glossary_store = _get_glossary_store()
    await glossary_store.set_e1rm(exercise_id, value_kg, method=method)
    return {"status": "e1rm_set", "id": exercise_id, "value_kg": value_kg}