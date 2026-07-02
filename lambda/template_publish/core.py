from __future__ import annotations
import asyncio
_store = None
def _get_store():
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _store

_template_store = None
def _get_template_store():
    global _template_store
    if _template_store is None:
        import os
        from template_store import TemplateStore
        _template_store = TemplateStore(
            table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
            pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _template_store

import copy
import uuid

def _template_actor(actor_pk):
    return str(actor_pk or _get_store().pk)

def _template_author(author, actor_pk):
    return str(author or actor_pk or _template_actor(actor_pk))

def _template_days_per_week(sessions):
    by_week = {}
    for session in sessions:
        try:
            week_number = int(session.get("week_number") or 1)
        except (TypeError, ValueError):
            week_number = 1
        raw_day = session.get("day_index") or session.get("day_of_week") or session.get("label") or "1"
        by_week.setdefault(week_number, set()).add(str(raw_day))
    return max((len(days) for days in by_week.values()), default=0)

def _template_normalize_day(session):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day = session.get("day_of_week")
    day_index = session.get("day_index")
    if isinstance(day, str) and day in weekdays:
        session["day_index"] = weekdays.index(day) + 1
        return
    try:
        idx = int(day_index)
    except (TypeError, ValueError):
        idx = 1
    idx = max(1, min(7, idx))
    session["day_index"] = idx
    session["day_of_week"] = weekdays[idx - 1]

def _prepare_template_payload(template):
    prepared = copy.deepcopy(template)
    meta = prepared.setdefault("meta", {})
    sessions = prepared.setdefault("sessions", [])
    phases = prepared.setdefault("phases", [])
    if not isinstance(sessions, list):
        prepared["sessions"] = sessions = []
    if not isinstance(phases, list):
        prepared["phases"] = []
    resolved = set()
    unresolved = set()
    required_maxes = set()
    max_week = 0
    for session in sessions:
        if not isinstance(session, dict):
            continue
        session.setdefault("id", str(uuid.uuid4()))
        try:
            week_number = int(session.get("week_number") or 1)
        except (TypeError, ValueError):
            week_number = 1
        week_number = max(1, week_number)
        session["week_number"] = week_number
        max_week = max(max_week, week_number)
        _template_normalize_day(session)
        session.setdefault("label", f"W{week_number}D{session.get('day_index', 1)}")
        exercises = session.get("exercises")
        if not isinstance(exercises, list):
            session["exercises"] = exercises = []
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue
            exercise.setdefault("notes", "")
            exercise.setdefault("sets", None)
            exercise.setdefault("reps", None)
            load_type = str(exercise.get("load_type") or "unresolvable").lower()
            if load_type not in {"rpe", "percentage", "absolute", "unresolvable"}:
                load_type = "unresolvable"
            exercise["load_type"] = load_type
            if load_type == "percentage":
                try:
                    load_value = float(exercise.get("load_value"))
                    if load_value > 1:
                        load_value = load_value / 100.0
                    exercise["load_value"] = load_value
                except (TypeError, ValueError):
                    exercise["load_value"] = None
                    exercise["load_type"] = "unresolvable"
            gid = exercise.get("glossary_id")
            if gid:
                gid = str(gid)
                exercise["glossary_id"] = gid
                resolved.add(gid)
                if exercise["load_type"] in {"percentage", "rpe"}:
                    required_maxes.add(gid)
            else:
                name = str(exercise.get("name") or "").strip()
                if name:
                    unresolved.add(name)
    if not max_week:
        max_week = max([int(s.get("week_number") or 1) for s in sessions if isinstance(s, dict)] or [0])
    meta.setdefault("name", "Imported Template")
    meta.setdefault("description", "")
    meta.setdefault("estimated_weeks", max_week)
    meta.setdefault("days_per_week", _template_days_per_week(sessions))
    meta.setdefault("archived", False)
    prepared["required_maxes"] = sorted(required_maxes)
    prepared["glossary_resolution"] = {
        "resolved": sorted(resolved),
        "unresolved": sorted(unresolved),
        "auto_added": [],
        "resolution_status": "partial" if resolved and unresolved else ("unresolved" if unresolved else "resolved"),
    }
    return prepared

async def template_publish(sk, actor_pk=None):
    ts = _get_template_store()
    await ts.set_published(sk, True, actor_pk=_template_actor(actor_pk))
    return {"status": "published", "sk": sk}