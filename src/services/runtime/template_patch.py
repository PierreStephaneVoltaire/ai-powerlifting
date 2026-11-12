import copy
import hashlib
import json
from typing import Callable

from services.runtime.exercise_names import normalize

PRESCRIPTION_FIELDS = ("sets", "reps", "load_type", "load_value", "rpe_target", "notes")
Resolver = Callable[[str], dict | None]


def patch_hash(sk: str, operations: list[dict]) -> str:
    return hashlib.sha256(json.dumps({"sk": sk, "operations": operations}, sort_keys=True, default=str).encode()).hexdigest()


def _in_scope(session: dict, operation: dict) -> bool:
    weeks = operation.get("weeks")
    days = operation.get("days") or ([operation["day_of_week"]] if operation.get("day_of_week") else None)
    week_ok = not weeks or int(session.get("week_number") or 0) in {int(week) for week in weeks}
    day_ok = not days or str(session.get("day_of_week") or "").lower() in {str(day).lower() for day in days}
    return week_ok and day_ok


def _matches(exercise: dict, name: str, resolve: Resolver) -> bool:
    if normalize(exercise.get("name")) == normalize(name):
        return True
    entry = resolve(name)
    return bool(entry and exercise.get("glossary_id") and str(exercise["glossary_id"]) == str(entry.get("id")))


def _snapshot(exercise: dict) -> dict:
    return {key: exercise.get(key) for key in ("name", *PRESCRIPTION_FIELDS) if exercise.get(key) is not None}


def _rename(exercise: dict, name: str, resolve: Resolver) -> None:
    entry = resolve(name)
    exercise["name"] = (entry or {}).get("name") or name
    if entry and entry.get("id"):
        exercise["glossary_id"] = str(entry["id"])
    else:
        exercise.pop("glossary_id", None)


def apply_operations(template: dict, operations: list[dict], resolve: Resolver) -> tuple[dict, list[dict], list[dict]]:
    patched = copy.deepcopy(template)
    changes: list[dict] = []
    unmatched: list[dict] = []
    for index, operation in enumerate(operations):
        kind = operation.get("op")
        touched = 0
        for session in patched.get("sessions") or []:
            if not _in_scope(session, operation):
                continue
            where = {"op": index, "week": session.get("week_number"), "day": session.get("day_of_week")}
            exercises = session.setdefault("exercises", [])
            if kind == "add_exercise":
                added = {"name": operation["name"], **{key: operation[key] for key in PRESCRIPTION_FIELDS if key in operation}}
                _rename(added, operation["name"], resolve)
                exercises.append(added)
                changes.append({**where, "before": None, "after": _snapshot(added)})
                touched += 1
                continue
            target = operation.get("from") if kind == "replace_exercise" else operation.get("exercise")
            for exercise in list(exercises):
                if not _matches(exercise, target or "", resolve):
                    continue
                before = _snapshot(exercise)
                if kind == "replace_exercise":
                    _rename(exercise, operation["to"], resolve)
                elif kind == "set_prescription":
                    exercise.update({key: operation[key] for key in PRESCRIPTION_FIELDS if key in operation})
                elif kind == "remove_exercise":
                    exercises.remove(exercise)
                    changes.append({**where, "before": before, "after": None})
                    touched += 1
                    continue
                else:
                    continue
                changes.append({**where, "before": before, "after": _snapshot(exercise)})
                touched += 1
        if not touched:
            unmatched.append({"op": index, "operation": operation})
    return patched, changes, unmatched
