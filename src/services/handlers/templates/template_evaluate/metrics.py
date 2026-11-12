from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from services import analytics_client
from services.lib.exercise_names import GLOSSARY_NAMES, competition_lift, normalize as _normalize
from services.lib.lift_calculations import RPE_PERCENT

USER_SELECTED_RPE = 8
FATIGUE_DIMENSIONS = ("axial", "neural", "peripheral", "systemic")
LIFTS = ("squat", "bench", "deadlift")
LOGGED_ONLY_SECTIONS = {
    "week", "window_start", "window_end", "selected_session_context", "compliance", "estimated_dots", "estimated_dots_reason",
    "projections", "projection_reason", "projection_calibration", "readiness_score", "attempt_selection",
    "specificity_target_competition", "taper_quality", "peaking_timeline", "sessions_analyzed",
}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Glossary:
    def __init__(self, exercises: list[dict]):
        self.by_id = {str(entry.get("id")): entry for entry in exercises if entry.get("id")}
        self.by_name = {_normalize(entry.get("name")): entry for entry in exercises if entry.get("name")}

    def resolve(self, exercise: dict) -> dict | None:
        entry = self.by_id.get(str(exercise.get("glossary_id") or ""))
        if entry:
            return entry
        entry = self.by_name.get(_normalize(exercise.get("name")))
        if entry:
            return entry
        lift = competition_lift(exercise.get("name", ""))
        return self.by_name.get(_normalize(GLOSSARY_NAMES[lift])) if lift else None


def load_mode(exercise: dict) -> tuple[str, float | None]:
    load_type = str(exercise.get("load_type") or "").lower()
    value = _number(exercise.get("load_value"))
    if load_type == "absolute" and value:
        return "absolute", value
    if load_type in ("percentage", "percent") and value:
        return "percentage", value / 100 if value > 1.5 else value
    if load_type == "rpe" and value:
        return "rpe", value
    rpe = _number(exercise.get("rpe_target"))
    if rpe:
        return "rpe", rpe
    return "user_selected", float(USER_SELECTED_RPE)


def _round(value: float, digits: int = 1) -> float:
    return round(value, digits)


def _glossary_e1rm(entry: dict | None) -> float | None:
    raw = (entry or {}).get("e1rm_estimate") or (entry or {}).get("e1rm")
    if isinstance(raw, dict):
        raw = raw.get("value_kg") or raw.get("kg") or raw.get("e1rm_kg") or raw.get("estimate_kg")
    return _number(raw)


def _planned_kg(exercise: dict, entry: dict | None, lift: str | None, maxes: dict) -> tuple[float | None, str | None]:
    mode, value = load_mode(exercise)
    if mode == "absolute":
        return value, "prescribed_kg"
    e1rm = maxes.get(lift) if lift else _glossary_e1rm(entry)
    reps = _number(exercise.get("reps")) or 0
    if mode == "percentage" and e1rm:
        return value * e1rm, "percent_of_e1rm"
    if mode in ("rpe", "user_selected") and e1rm:
        pct = RPE_PERCENT.get(f"{int(reps)}-{int(value)}")
        if pct:
            return pct * e1rm, "rpe_table_of_e1rm"
    return None, None


def _session_date(session: dict, week: int, start: date) -> date:
    day = str(session.get("day_of_week") or "").lower()
    offset = WEEKDAYS.index(day) if day in WEEKDAYS else int(_number(session.get("day_index")) or 0) % 7
    return start + timedelta(days=(week - 1) * 7 + offset)


def template_program(template: dict, glossary_exercises: list[dict], current_maxes: dict, lift_profiles: list[dict]) -> tuple[dict, dict]:
    glossary = Glossary(glossary_exercises)
    maxes = {lift: value for lift in LIFTS if (value := _number(current_maxes.get(lift)))}
    glossary_profiles = {entry.get("name", "").lower().strip() for entry in glossary_exercises if isinstance(entry.get("fatigue_profile"), dict) and all(dimension in entry["fatigue_profile"] for dimension in FATIGUE_DIMENSIONS)}
    today = date.today()
    start = today - timedelta(days=today.weekday())
    sessions, exercises = [], {}
    missing_from_glossary, load_not_computable = set(), set()
    top_sets: dict[int, dict[str, float]] = defaultdict(dict)

    for session in template.get("sessions") or []:
        week = int(_number(session.get("week_number")) or 0)
        if week <= 0:
            continue
        planned = []
        for exercise in session.get("exercises") or []:
            sets = _number(exercise.get("sets")) or 0
            reps = _number(exercise.get("reps")) or 0
            if sets <= 0:
                continue
            name = exercise.get("name", "")
            entry = glossary.resolve(exercise)
            lift = competition_lift(name)
            category = (entry or {}).get("category")
            variation = None if lift else (category if category in LIFTS else None)
            canonical = GLOSSARY_NAMES[lift] if lift else ((entry or {}).get("name") or name)
            mode, value = load_mode(exercise)
            kg, load_source = _planned_kg(exercise, entry, lift, maxes)
            if canonical.lower().strip() not in glossary_profiles:
                missing_from_glossary.add(name)
            if kg and reps > 0:
                planned.append({"name": canonical, "kg": _round(kg, 2), "reps": int(reps), "sets": sets, "rpe": value if mode in ("rpe", "user_selected") else None})
                if lift:
                    top_sets[week][lift] = max(kg, top_sets[week].get(lift, 0.0))
            else:
                load_not_computable.add(name)
            summary = exercises.setdefault(name, {
                "glossary_match": (entry or {}).get("name"),
                "role": "competition_lift" if lift else ("variation" if variation else "accessory"),
                "lift": lift or variation,
                "load_modes": set(), "planned_load_sources": set(), "weeks": set(),
            })
            summary["load_modes"].add(mode)
            if load_source:
                summary["planned_load_sources"].add(load_source)
            summary["weeks"].add(week)
        sessions.append({
            "date": _session_date(session, week, start).isoformat(),
            "week_number": week,
            "day": session.get("day_of_week"),
            "completed": True,
            "status": "logged",
            "exercises": planned,
        })

    phases = [
        {
            "name": phase.get("name"),
            "intent": phase.get("intent"),
            "start_week": int(_number(phase.get("week_start")) or 0),
            "end_week": int(_number(phase.get("week_end")) or 0),
            "target_rpe_min": phase.get("target_rpe_min"),
            "target_rpe_max": phase.get("target_rpe_max"),
        }
        for phase in template.get("phases") or []
    ]
    program = {
        "meta": {"program_start": start.isoformat(), "current_block_id": "current"},
        "phases": phases,
        "sessions": sessions,
        "current_maxes": maxes,
        "lift_profiles": lift_profiles,
        "competitions": [],
    }
    summary = {
        "exercises": {
            name: {**entry, "load_modes": sorted(entry["load_modes"]), "planned_load_sources": sorted(entry["planned_load_sources"]), "weeks": f"{min(entry['weeks'])}-{max(entry['weeks'])}"}
            for name, entry in exercises.items()
        },
        "top_set_pct_of_current_max_by_week": {
            str(week): {lift: _round(kg / maxes[lift] * 100) for lift, kg in sorted(lifts.items()) if maxes.get(lift)}
            for week, lifts in sorted(top_sets.items())
        },
        "missing_from_glossary": sorted(missing_from_glossary),
        "load_not_computable": sorted(load_not_computable),
    }
    return program, summary


def template_metrics(template: dict, glossary_exercises: list[dict], current_maxes: dict, lift_profiles: list[dict] | None = None) -> dict:
    program, summary = template_program(template, glossary_exercises, current_maxes, lift_profiles or [])
    sessions = program["sessions"]
    if not sessions:
        return {"weeks": 0}
    weeks = max(session["week_number"] for session in sessions)
    end = max(session["date"] for session in sessions)
    report = analytics_client.weekly_analysis(program, sessions, week_start=1, week_end=weeks, ref_date=end, block="", current_maxes=program["current_maxes"])
    return {
        "weeks": weeks,
        "analysis": {key: value for key, value in report.items() if key not in LOGGED_ONLY_SECTIONS},
        "template": summary,
        "notes": [
            "analysis is the app's weekly analysis report computed on this template alone, as if every planned session were completed as written. No logged training is included.",
            "Planned kg comes from the prescription, or the percent or RPE table applied to the current max (competition lifts) or the glossary e1RM (other exercises).",
            "missing_from_glossary exercises fall back to the app's default fatigue profile; load_not_computable exercises have no kg and are excluded from load-based metrics.",
            f"Exercises without a prescribed load are user-selected and counted at RPE {USER_SELECTED_RPE}.",
        ],
    }


def strip_calendar(template: dict) -> dict:
    sessions = [{key: value for key, value in session.items() if key not in ("date", "id")} for session in template.get("sessions") or []]
    meta = {key: value for key, value in (template.get("meta") or {}).items() if key in ("name", "program_context", "estimated_weeks", "days_per_week")}
    return {"meta": meta, "phases": template.get("phases") or [], "sessions": sessions}
