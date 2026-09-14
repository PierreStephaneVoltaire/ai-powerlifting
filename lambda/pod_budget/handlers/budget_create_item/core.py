from __future__ import annotations

import os


def _get_store():
    from _budget_store import BudgetStore as _BS
    _store = _BS(
        table_name=os.environ.get("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _store


async def budget_create_item(args: dict) -> dict:
    """Create a new budget item.

    Args:
        args: dict with optional `pk`, and required `item` (raw item body).
    """
    store = _get_store()
    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    raw = args.get("item") or {}
    return await store.create_item(pk, raw)
