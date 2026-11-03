from __future__ import annotations

import os
from datetime import datetime, timezone


def _get_store():
    from services.handlers.budget._budget_store import BudgetStore as _BS
    _store = _BS(
        table_name=os.environ.get("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _store


async def budget_get_summary(args: dict) -> dict:
    """Get the budget summary (spent, recurring, breakdown) for a month.

    Args:
        args: dict with optional `pk`, and required `month` (YYYY-MM).
    """
    store = _get_store()
    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    month = args.get("month") or datetime.now(timezone.utc).isoformat()[:7]
    return await store.get_summary(pk, month, args.get("block_id"))
