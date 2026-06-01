from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

CITY_TIMEZONES: Dict[str, str] = {
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "phoenix": "America/Phoenix",
    "philadelphia": "America/New_York",
    "san antonio": "America/Chicago",
    "san diego": "America/Los_Angeles",
    "dallas": "America/Chicago",
    "san jose": "America/Los_Angeles",
    "toronto": "America/Toronto",
    "montreal": "America/Montreal",
    "vancouver": "America/Vancouver",
    "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "rio de janeiro": "America/Sao_Paulo",
    "santiago": "America/Santiago",
    "lima": "America/Lima",
    "bogota": "America/Bogota",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid",
    "rome": "Europe/Rome",
    "amsterdam": "Europe/Amsterdam",
    "brussels": "Europe/Brussels",
    "vienna": "Europe/Vienna",
    "prague": "Europe/Prague",
    "warsaw": "Europe/Warsaw",
    "stockholm": "Europe/Stockholm",
    "oslo": "Europe/Oslo",
    "copenhagen": "Europe/Copenhagen",
    "helsinki": "Europe/Helsinki",
    "dublin": "Europe/Dublin",
    "lisbon": "Europe/Lisbon",
    "athens": "Europe/Athens",
    "zurich": "Europe/Zurich",
    "tokyo": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
    "bangkok": "Asia/Bangkok",
    "mumbai": "Asia/Kolkata",
    "dubai": "Asia/Dubai",
    "istanbul": "Europe/Istanbul",
    "jakarta": "Asia/Jakarta",
    "manila": "Asia/Manila",
    "cairo": "Africa/Cairo",
    "lagos": "Africa/Lagos",
    "johannesburg": "Africa/Johannesburg",
    "nairobi": "Africa/Nairobi",
    "casablanca": "Africa/Casablanca",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
}

def _get_city_time(city: str) -> Dict[str, Any]:
    normalized = city.strip().lower()
    tz_name = CITY_TIMEZONES.get(normalized)
    if not tz_name:
        return {
            "error": f"City '{city}' not recognized.",
            "supported_cities": sorted(CITY_TIMEZONES.keys()),
        }

    now = datetime.now(ZoneInfo(tz_name))
    utc_offset = now.strftime("%z")
    formatted_offset = f"{utc_offset[:3]}:{utc_offset[3:]}"

    return {
        "city": normalized.title(),
        "timezone": tz_name,
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "utc_offset": formatted_offset,
        "day_of_week": now.strftime("%A"),
    }

async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "get_city_time":
        result = _get_city_time(args["city"])
        return _format_result(result)
    return f"Unknown temporal_city_time tool: {name}"
