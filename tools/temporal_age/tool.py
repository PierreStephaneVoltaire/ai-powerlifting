from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)

_ZODIAC = [
    ((1, 20), (2, 18), "Aquarius"),
    ((2, 19), (3, 20), "Pisces"),
    ((3, 21), (4, 19), "Aries"),
    ((4, 20), (5, 20), "Taurus"),
    ((5, 21), (6, 20), "Gemini"),
    ((6, 21), (7, 22), "Cancer"),
    ((7, 23), (8, 22), "Leo"),
    ((8, 23), (9, 22), "Virgo"),
    ((9, 23), (10, 22), "Libra"),
    ((10, 23), (11, 21), "Scorpio"),
    ((11, 22), (12, 21), "Sagittarius"),
    ((12, 22), (1, 19), "Capricorn"),
]

def _zodiac_sign(month: int, day: int) -> str:
    for start, end, sign in _ZODIAC:
        if start <= end:
            if start <= (month, day) <= end:
                return sign
        else:
            if (month, day) >= start or (month, day) <= end:
                return sign
    return "Unknown"

def _calculate_age(birth_date_str: str, reference_date_str: Optional[str] = None) -> Dict[str, Any]:
    import dateparser
    from dateutil.relativedelta import relativedelta

    birth = dateparser.parse(birth_date_str)
    if birth is None:
        return {"error": f"Could not parse birth_date: {birth_date_str!r}"}

    if reference_date_str:
        ref = dateparser.parse(reference_date_str)
        if ref is None:
            return {"error": f"Could not parse reference_date: {reference_date_str!r}"}
    else:
        ref = datetime.now()

    age = relativedelta(ref, birth)

    try:
        next_bday = birth.replace(year=ref.year)
        if next_bday < ref.date() if hasattr(ref, 'date') else next_bday < ref:
            next_bday = next_bday.replace(year=ref.year + 1)
        days_until = (next_bday - (ref.date() if hasattr(ref, 'date') else ref)).days
    except ValueError:
        next_bday = birth.replace(year=ref.year, day=28)
        if next_bday < (ref.date() if hasattr(ref, 'date') else ref):
            next_bday = birth.replace(year=ref.year + 1, day=28)
        days_until = (next_bday - (ref.date() if hasattr(ref, 'date') else ref)).days

    return {
        "years": age.years,
        "months": age.months,
        "days": age.days,
        "next_birthday": next_bday.strftime("%Y-%m-%d"),
        "days_until_birthday": days_until,
        "zodiac_sign": _zodiac_sign(birth.month, birth.day),
    }

async def execute(name: str, args: Dict[str, Any]) -> str:
    if name == "calculate_age":
        result = _calculate_age(args["birth_date"], args.get("reference_date"))
        return _format_result(result)
    return f"Unknown temporal_age tool: {name}"
