from __future__ import annotations

import json
import re
from pathlib import Path

LIFTS = ("squat", "bench", "deadlift")
_RULES = json.loads((Path(__file__).parent / "lift_transfer_rules.json").read_text())
_NAME_LIFTS = {"squat": "squat", "bench": "bench", "deadlift": "deadlift"}


def _name_lift(name: str) -> str | None:
    match = re.search(r"\b(squat|bench|deadlift)\b", name)
    return _NAME_LIFTS[match.group(1)] if match else None


def _transfer(values: dict[str, float], reasoning: str) -> dict:
    return {
        "squat": values.get("squat", 0.0),
        "bench": values.get("bench", 0.0),
        "deadlift": values.get("deadlift", 0.0),
        "source": "rule",
        "reasoning": reasoning,
    }


def rule_lift_transfer(exercise: dict) -> dict:
    name = re.sub(r"\s+", " ", str(exercise.get("name") or "").lower()).strip()
    name_lift = _name_lift(name)
    for rule in _RULES["name_rules"]:
        if not re.search(rule["pattern"], name):
            continue
        lift = name_lift if rule["lift"] == "$name" else rule["lift"]
        if lift is None:
            continue
        return _transfer({lift: rule["value"]}, f"Rule {rule['id']}: {lift} {rule['value']}")
    category = str(exercise.get("category") or "").lower()
    if category in _RULES["category_variation"]:
        value = _RULES["category_variation"][category]
        return _transfer({category: value}, f"Rule category_variation: {category} {value}")
    isolation = _RULES["isolation"]
    values: dict[str, float] = {}
    for field, value in (("secondary_muscles", isolation["secondary_value"]), ("primary_muscles", isolation["primary_value"])):
        for muscle in exercise.get(field) or []:
            for lift in isolation["muscle_lifts"].get(muscle, []):
                values[lift] = max(values.get(lift, 0.0), value)
    return _transfer(values, "Rule isolation: muscle-based default capped at " + str(isolation["primary_value"]))


def ensure_lift_transfer(exercise: dict) -> dict:
    if exercise.get("lift_transfer"):
        return exercise
    return {**exercise, "lift_transfer": rule_lift_transfer(exercise)}
