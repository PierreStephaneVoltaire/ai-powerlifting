from __future__ import annotations

import json
from typing import Any, Dict

def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

def _datetime_to_unix(datetime_str: str) -> Dict[str, Any]:
    import dateparser

    parsed = dateparser.parse(datetime_str)
    if parsed is None:
        return {"error": f"Could not parse datetime string: {datetime_str!r}"}

    return {
        "unix_timestamp": int(parsed.timestamp()),
        "iso8601": parsed.isoformat(),
        "human_readable": parsed.strftime("%B %d, %Y at %I:%M %p"),
    }

async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "datetime_to_unix":
        result = _datetime_to_unix(args["datetime_str"])
        return _format_result(result)
    return f"Unknown temporal_to_unix tool: {name}"
