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


async def exercise_set_e1rm(args: dict) -> dict:
    """Set an e1rm estimate on an exercise (mirrors backend setE1rmEstimate).

    Args:
        args: dict with optional `pk`, required `id`, `value_kg` (number),
              and optional `method` ('manual' | 'ai_backfill' | 'logged',
              defaults to 'manual').
    """
    store = _get_glossary_store()
    if args.get("pk"):
        store.pk = args["pk"]
    exercise_id = args.get("id") or ""
    value_kg = float(args.get("value_kg") or 0)
    method = args.get("method") or "manual"
    confidence = "medium" if method == "manual" else "low"
    basis = "Manual entry" if method == "manual" else ""
    manually_overridden = method == "manual"
    await store.set_e1rm(
        exercise_id,
        value_kg,
        method=method,
        basis=basis,
        confidence=confidence,
        manually_overridden=manually_overridden,
    )
    return {"status": "e1rm_set", "id": exercise_id, "value_kg": value_kg, "method": method}