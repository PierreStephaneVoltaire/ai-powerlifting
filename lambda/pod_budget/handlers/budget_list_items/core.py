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


async def budget_list_items(args: dict) -> dict:
    """List budget items, optionally filtered by comp_id/category/priority.

    Args:
        args: dict with optional `pk`, and optional filter keys `comp_id`,
              `category`, `priority` (priority_tier).
    """
    store = _get_store()
    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    store.pk = pk
    filters = {}
    if args.get("comp_id") is not None:
        filters["comp_id"] = args.get("comp_id")
    if args.get("category") is not None:
        filters["category"] = args.get("category")
    if args.get("priority") is not None:
        filters["priority"] = args.get("priority")
    items = await store.list_items(pk, filters or None)
    return {"items": items}