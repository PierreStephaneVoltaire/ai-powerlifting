from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from importlib import import_module
from typing import Any

from . import analytics
from .core import _get_store


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    return str(obj)


async def suggest_e1rm_multipliers(args: dict[str, Any]) -> dict[str, Any]:
    program = args.get("program")
    if not isinstance(program, dict):
        program = await _get_store().get_program()
    max_history = args.get("max_history")
    if max_history is None:
        max_history_get = import_module("services.handlers.maxes.max_history_get.core").max_history_get
        history_item = await max_history_get(args)
        max_history = history_item.get("entries", [])
    reference_date = analytics._parse_date(args.get("reference_date", ""))
    return analytics.compute_e1rm_multiplier_suggestions(
        program,
        max_history=max_history if isinstance(max_history, list) else [],
        reference_date=reference_date or date.today(),
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    args = event.get("args", event)
    result = asyncio.run(suggest_e1rm_multipliers(args))
    return {"statusCode": 200, "body": json.dumps(result, default=_json_default)}
