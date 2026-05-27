"""Temporal resolve tool plugin — parse natural language date/time phrases into concrete dates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)


def _resolve_phrase(phrase: str, tz: Optional[str] = None) -> Dict[str, Any]:
    import dateparser

    now_utc = datetime.now(timezone.utc)
    parsed = dateparser.parse(
        phrase,
        settings={
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": now_utc,
        },
    )
    if parsed is None:
        return {"error": f"Could not parse phrase: {phrase!r}", "phrase": phrase}

    # Ensure UTC-aware for comparisons
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    is_past = parsed < now_utc
    diff = parsed - now_utc if not is_past else now_utc - parsed
    days = abs(diff.days)

    if days == 0:
        relative = "today"
    elif days == 1:
        relative = "tomorrow" if not is_past else "yesterday"
    elif days < 7:
        relative = f"in {days} days" if not is_past else f"{days} days ago"
    elif days < 30:
        weeks = days // 7
        relative = f"in {weeks} week{'s' if weeks != 1 else ''}" if not is_past else f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif days < 365:
        months = days // 30
        relative = f"in ~{months} month{'s' if months != 1 else ''}" if not is_past else f"~{months} month{'s' if months != 1 else ''} ago"
    else:
        years = days // 365
        relative = f"in ~{years} year{'s' if years != 1 else ''}" if not is_past else f"~{years} year{'s' if years != 1 else ''} ago"

    result: Dict[str, Any] = {
        "phrase": phrase,
        "utc": parsed.isoformat(),
        "date": parsed.strftime("%Y-%m-%d"),
        "time_utc": parsed.strftime("%H:%M:%S"),
        "day_of_week": parsed.strftime("%A"),
        "relative_description": relative,
        "is_past": is_past,
    }

    if tz:
        try:
            from zoneinfo import ZoneInfo
            local = parsed.astimezone(ZoneInfo(tz))
            result["local"] = local.isoformat()
            result["local_date"] = local.strftime("%Y-%m-%d")
            result["local_time"] = local.strftime("%H:%M:%S")
            result["local_offset"] = local.strftime("%z")
            result["local_tz"] = tz
            result["day_of_week"] = local.strftime("%A")
        except Exception as e:
            result["tz_error"] = f"Could not convert to {tz!r}: {e}"

    return result


async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "resolve_temporal_phrase":
        result = _resolve_phrase(args["phrase"], args.get("tz"))
        return _format_result(result)
    return f"Unknown temporal_resolve tool: {name}"
