from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    global _store
    if _store is None:
        from _budget_store import BudgetStore as _BS
        _store = _BS(
            table_name=os.environ.get("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[BudgetTools] BudgetStore initialised from env vars")
    return _store


async def budget_create_item(args: dict) -> dict:
    """Create a new budget item.

    Args:
        args: dict with optional `pk`, and required `item` (raw item body).
    """
    store = _get_store()
    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    store.pk = pk
    raw = args.get("item") or {}
    return await store.create_item(pk, raw)