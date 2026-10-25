import copy
from decimal import Decimal
from typing import Any

PER_SET_FIELDS = ("sets_data", "set_ids", "set_statuses", "failed_sets", "failed_set_reasons")


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def _at(values: Any, index: int, default: Any = None) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else default


def expand_performed_sets(exercise: dict[str, Any]) -> list[dict[str, Any]]:
    sets_data = exercise.get("sets_data")
    if not isinstance(sets_data, list) or not any(isinstance(item, dict) for item in sets_data):
        return [exercise]
    performed = [item if isinstance(item, dict) else {} for item in sets_data]
    values = [tuple(_value(item.get(key, exercise.get(key))) for key in ("reps", "kg", "rpe")) for item in performed]
    statuses = [_at(exercise.get("set_statuses"), index) for index in range(len(performed))]
    failures = [bool(_at(exercise.get("failed_sets"), index, False)) for index in range(len(performed))]
    reasons = [_at(exercise.get("failed_set_reasons"), index, []) for index in range(len(performed))]
    if len(set(values)) == 1 and len(set(statuses)) == 1 and not any(failures):
        reps, kg, rpe = values[0]
        return [{**exercise, "sets": len(performed), "reps": reps, "kg": kg, "rpe": rpe}]
    base = {key: value for key, value in exercise.items() if key not in PER_SET_FIELDS}
    expanded = []
    for index, (reps, kg, rpe) in enumerate(values):
        row = copy.deepcopy(base)
        row.update(
            sets=1, reps=reps, kg=kg, rpe=rpe, set_number=index + 1,
            failed=failures[index], failed_sets=[failures[index]], failed_set_reasons=[reasons[index]],
            notes=exercise.get("notes", "") if index == 0 else "",
        )
        if statuses[index] is not None:
            row["set_statuses"] = [statuses[index]]
        if exercise.get("id"):
            row["id"] = f"{exercise['id']}-set{index + 1}"
        expanded.append(row)
    return expanded


def expand_session_sets(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded = []
    for session in sessions:
        exercises = session.get("exercises")
        if isinstance(exercises, list):
            session = {**session, "exercises": [row for exercise in exercises if isinstance(exercise, dict) for row in expand_performed_sets(exercise)]}
        expanded.append(session)
    return expanded
