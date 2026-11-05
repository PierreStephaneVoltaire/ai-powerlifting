import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

LIFTS = ("squat", "bench", "deadlift")
NOTES_LIMIT = 1000
DROPPED = ("style_notes", "sticking_points", "primary_muscle", "failure_nodes")


@lru_cache(maxsize=1)
def definitions() -> dict[str, list[dict]]:
    return json.loads((Path(__file__).resolve().parents[1] / "lift_profile_options.json").read_text())


def fields(lift: str) -> list[dict]:
    return definitions().get(lift, [])


def _common() -> dict:
    return {field["key"]: field for field in definitions()["common"]}


def _valid(field: dict, value: Any) -> str | None:
    value = str(value or "").strip()
    return value if value in {option["value"] for option in field["options"]} else None


def clean_options(lift: str, options: Any) -> dict[str, str]:
    options = options if isinstance(options, dict) else {}
    cleaned = {}
    for field in fields(lift):
        value = _valid(field, options.get(field["key"]))
        if value:
            cleaned[field["key"]] = value
    for field in fields(lift):
        lock = field.get("locked")
        if lock and all(cleaned.get(key) == value for key, value in lock["when"].items()):
            cleaned[field["key"]] = lock["value"]
    return cleaned


def clean(profile: Any) -> dict | None:
    if not isinstance(profile, dict) or profile.get("lift") not in LIFTS:
        return None
    lift = profile["lift"]
    result = {key: value for key, value in profile.items() if key not in DROPPED}
    result["options"] = clean_options(lift, profile.get("options"))
    result["volume_tolerance"] = _valid(_common()["volume_tolerance"], profile.get("volume_tolerance")) or "moderate"
    result["notes"] = str(profile.get("notes") or "").strip()[:NOTES_LIMIT]
    return result


def missing(profile: dict) -> list[str]:
    options = (profile or {}).get("options") or {}
    return [field["label"] for field in fields((profile or {}).get("lift", "")) if not options.get(field["key"])]


def describe(profile: dict) -> dict:
    lift = (profile or {}).get("lift", "")
    options = (profile or {}).get("options") or {}
    labels = {}
    for field in fields(lift):
        value = options.get(field["key"])
        option = next((option for option in field["options"] if option["value"] == value), None)
        if option:
            labels[field["label"]] = option["label"]
    described = {"lift": lift, "technique": labels, "volume_tolerance": (profile or {}).get("volume_tolerance") or "moderate"}
    if (profile or {}).get("notes"):
        described["notes"] = profile["notes"]
    return described


def suggest_tool_schema(lift: str) -> dict:
    properties = {
        field["key"]: {"type": ["string", "null"], "enum": [option["value"] for option in field["options"]] + [None], "description": field["label"]}
        for field in fields(lift)
    }
    properties["volume_tolerance"] = {"type": ["string", "null"], "enum": ["low", "moderate", "high", None]}
    return {
        "type": "function",
        "function": {
            "name": "select_lift_profile_options",
            "description": f"Select the {lift} technique options that match the lifter's description. Use null when the description does not say.",
            "parameters": {"type": "object", "properties": properties, "required": list(properties)},
        },
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def technique_lines(profile: dict) -> list[str]:
    described = describe(profile)
    lines = [f"{label}: {value}" for label, value in described["technique"].items()]
    lines.append(f"Volume tolerance: {described['volume_tolerance']}")
    if described.get("notes"):
        lines.append(f"Notes: {described['notes']}")
    return lines


def technique_text(profile: dict) -> str:
    return "; ".join(f"{label}: {value}" for label, value in describe(profile)["technique"].items())
