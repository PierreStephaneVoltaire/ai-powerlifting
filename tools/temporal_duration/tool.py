from __future__ import annotations

import json
from typing import Any, Dict

def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

def _calculate_duration(start_date_str: str, end_date_str: str) -> Dict[str, Any]:
    import dateparser
    from dateutil.relativedelta import relativedelta

    start = dateparser.parse(start_date_str)
    if start is None:
        return {"error": f"Could not parse start_date: {start_date_str!r}"}

    end = dateparser.parse(end_date_str)
    if end is None:
        return {"error": f"Could not parse end_date: {end_date_str!r}"}

    delta = relativedelta(end, start)
    total_days = (end - start).days
    weeks = total_days // 7

    parts = []
    if delta.years:
        parts.append(f"{delta.years} year{'s' if delta.years != 1 else ''}")
    if delta.months:
        parts.append(f"{delta.months} month{'s' if delta.months != 1 else ''}")
    if delta.days:
        parts.append(f"{delta.days} day{'s' if delta.days != 1 else ''}")

    description = ", ".join(parts) if parts else "0 days"

    return {
        "years": delta.years,
        "months": delta.months,
        "days": delta.days,
        "weeks": weeks,
        "hours": abs(total_days * 24),
        "total_days": total_days,
        "description": description,
    }

async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "time_duration":
        result = _calculate_duration(args["start_date"], args["end_date"])
        return _format_result(result)
    return f"Unknown temporal_duration tool: {name}"
