from __future__ import annotations

import json
from typing import Any, Dict

def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

def _convert_timezone(datetime_str: str, from_tz: str, to_tz: str) -> Dict[str, Any]:
    import dateparser
    from zoneinfo import ZoneInfo

    parsed = dateparser.parse(datetime_str)
    if parsed is None:
        return {"error": f"Could not parse datetime: {datetime_str!r}"}

    try:
        from_zone = ZoneInfo(from_tz)
        to_zone = ZoneInfo(to_tz)
    except Exception as e:
        return {"error": f"Timezone lookup failed: {e}"}

    try:
        localized = parsed.replace(tzinfo=from_zone)
        converted = localized.astimezone(to_zone)
    except Exception as e:
        return {"error": f"Conversion failed: {e}"}

    def _fmt_offset(dt):
        utc_off = dt.strftime("%z")
        return f"{utc_off[:3]}:{utc_off[3:]}"

    return {
        "original": str(localized),
        "converted": str(converted),
        "from_tz": from_tz,
        "to_tz": to_tz,
        "from_offset": _fmt_offset(localized),
        "to_offset": _fmt_offset(converted),
    }

async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "convert_timezone":
        result = _convert_timezone(args["datetime_str"], args["from_tz"], args["to_tz"])
        return _format_result(result)
    return f"Unknown temporal_timezone tool: {name}"
