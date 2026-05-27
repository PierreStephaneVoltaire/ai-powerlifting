"""Temporal from-unix tool plugin — convert Unix timestamp to structured datetime."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)


def _relative_description(dt: datetime) -> str:
    from dateutil.relativedelta import relativedelta

    now = datetime.now(timezone.utc)
    diff = relativedelta(dt.replace(tzinfo=timezone.utc), now)
    total_days = (dt.replace(tzinfo=timezone.utc) - now).days
    is_future = total_days > 0
    days = abs(total_days)

    if days == 0:
        return "today"
    elif days == 1:
        return "tomorrow" if is_future else "yesterday"
    elif days < 7:
        return f"in {days} days" if is_future else f"{days} days ago"
    elif days < 30:
        weeks = days // 7
        return f"in {weeks} week{'s' if weeks != 1 else ''}" if is_future else f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif days < 365:
        months = days // 30
        return f"in ~{months} month{'s' if months != 1 else ''}" if is_future else f"~{months} month{'s' if months != 1 else ''} ago"
    else:
        years = days // 365
        return f"in ~{years} year{'s' if years != 1 else ''}" if is_future else f"~{years} year{'s' if years != 1 else ''} ago"


def _unix_to_datetime(unix_timestamp: float, tz: Optional[str] = None) -> Dict[str, Any]:
    try:
        ts = float(unix_timestamp)
    except (ValueError, TypeError):
        return {"error": f"Invalid timestamp: {unix_timestamp!r}"}

    # Auto-detect milliseconds
    if abs(ts) > 1e12:
        ts = ts / 1000.0

    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, OSError, OverflowError) as e:
        return {"error": f"Timestamp out of range: {e}"}

    result: Dict[str, Any] = {
        "unix_timestamp": int(unix_timestamp),
        "utc": dt.isoformat(),
        "date": dt.strftime("%Y-%m-%d"),
        "time_utc": dt.strftime("%H:%M:%S"),
        "day_of_week": dt.strftime("%A"),
        "human_readable": dt.strftime("%B %d, %Y at %I:%M %p UTC"),
        "relative_description": _relative_description(dt),
    }

    if tz:
        try:
            from zoneinfo import ZoneInfo
            local = dt.astimezone(ZoneInfo(tz))
            result["local"] = local.isoformat()
            result["local_date"] = local.strftime("%Y-%m-%d")
            result["local_time"] = local.strftime("%H:%M:%S")
            result["local_offset"] = local.strftime("%z")
            result["local_tz"] = tz
            result["human_readable"] = local.strftime("%B %d, %Y at %I:%M %p") + f" {local.strftime('%Z')}"
            result["day_of_week"] = local.strftime("%A")
        except Exception as e:
            result["tz_error"] = f"Could not convert to {tz!r}: {e}"

    return result


async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "unix_to_datetime":
        result = _unix_to_datetime(args["unix_timestamp"], args.get("tz"))
        return _format_result(result)
    return f"Unknown temporal_from_unix tool: {name}"
