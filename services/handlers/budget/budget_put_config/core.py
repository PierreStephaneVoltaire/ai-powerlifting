from __future__ import annotations

import os


def _get_store():
    from services.handlers.budget._budget_store import BudgetStore as _BS
    _store = _BS(
        table_name=os.environ.get("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _store


async def budget_put_config(args: dict) -> dict:
    """Upsert the budget config for a user.

    Args:
        args: dict with optional `pk`, and required `config` (raw config body
              with monthly_cap, currency, notes).
    """
    store = _get_store()
    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    raw = args.get("config") or {}
    return await store.put_config(pk, raw)
