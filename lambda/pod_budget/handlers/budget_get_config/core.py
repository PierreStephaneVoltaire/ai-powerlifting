from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the BudgetStore singleton."""
    global _store
    if _store is None:
        from budget_store import BudgetStore as _BS
        _store = _BS(
            table_name=os.environ.get("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[BudgetTools] BudgetStore initialised from env vars")
    return _store


async def budget_get_config(args: dict) -> dict:
    """Get the budget config for a user.

    Args:
        args: dict with optional `pk` (defaults to env HEALTH_PROGRAM_PK).
    """
    store = _get_store()
    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    store.pk = pk
    return await store.get_config(pk)