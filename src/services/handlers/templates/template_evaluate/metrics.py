from collections import defaultdict
from typing import Any

from services.lib.exercise_names import GLOSSARY_NAMES, competition_lift, normalize as _normalize

RPE_INTENSITY = {10: 1.0, 9.5: 0.98, 9: 0.96, 8.5: 0.94, 8: 0.92, 7.5: 0.9, 7: 0.88, 6.5: 0.86, 6: 0.84}
USER_SELECTED_RPE = 8
MUSCLE_WEIGHTS = {"primary_muscles": 1.0, "secondary_muscles": 0.5, "tertiary_muscles": 0.25}
FATIGUE_DIMENSIONS = ("axial", "neural", "peripheral", "systemic")


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


def _rpe_intensity(rpe: float) -> float:
    nearest = min(RPE_INTENSITY, key=lambda key: abs(key - rpe))
    return RPE_INTENSITY[nearest]


def _intensity(mode: str, value: float | None, lift: str | None, maxes: dict[str, float]) -> float:
    if mode == "absolute":
        current = maxes.get(lift or "")
        return min(value / current, 1.1) if current and value else 0.75
    if mode == "percentage":
        return value or 0.75
    return _rpe_intensity(value or USER_SELECTED_RPE)


def _phase_for(week: int, phases: list[dict]) -> str | None:
    for phase in phases:
        start, end = _number(phase.get("week_start")), _number(phase.get("week_end"))
        if start is not None and end is not None and start <= week <= end:
            return phase.get("name")
    return None


def _round(value: float, digits: int = 1) -> float:
    return round(value, digits)


def template_metrics(template: dict, glossary_exercises: list[dict], current_maxes: dict, specificity_band=None) -> dict:
    glossary = Glossary(glossary_exercises)
    maxes = {lift: value for lift in ("squat", "bench", "deadlift") if (value := _number(current_maxes.get(lift)))}
    phases = template.get("phases") or []
    weeks: dict[int, dict] = {}
    exercises: dict[str, dict] = {}
    length = 0

    for session in template.get("sessions") or []:
        week = int(_number(session.get("week_number")) or 0)
        if week <= 0:
            continue
        length = max(length, week)
        bucket = weeks.setdefault(week, {
            "sets": 0.0, "narrow": 0.0, "broad": 0.0, "days": set(),
            "muscles": defaultdict(float), "fatigue": defaultdict(float),
            "lifts": defaultdict(lambda: {"top_kg": 0.0, "sets": 0.0, "reps": 0.0}),
        })
        bucket["days"].add(session.get("day_of_week") or session.get("day_index"))
        for exercise in session.get("exercises") or []:
            sets = _number(exercise.get("sets")) or 0
            reps = _number(exercise.get("reps")) or 0
            if sets <= 0:
                continue
            entry = glossary.resolve(exercise)
            lift = competition_lift(exercise.get("name", ""))
            category = (entry or {}).get("category")
            variation = None if lift else (category if category in ("squat", "bench", "deadlift") else None)
            mode, value = load_mode(exercise)
            intensity = _intensity(mode, value, lift or variation, maxes)

            bucket["sets"] += sets
            if lift:
                bucket["narrow"] += sets
                bucket["broad"] += sets
                stats = bucket["lifts"][lift]
                stats["sets"] += sets
                stats["reps"] += sets * reps
                if mode == "absolute" and value:
                    stats["top_kg"] = max(stats["top_kg"], value)
            elif variation:
                bucket["broad"] += sets
            for field, weight in MUSCLE_WEIGHTS.items():
                for muscle in (entry or {}).get(field) or []:
                    bucket["muscles"][muscle] += sets * weight
            profile = (entry or {}).get("fatigue_profile") or {}
            for dimension in FATIGUE_DIMENSIONS:
                bucket["fatigue"][dimension] += sets * (_number(profile.get(dimension)) or 0) * intensity

            summary = exercises.setdefault(exercise.get("name", ""), {
                "glossary_match": (entry or {}).get("name"), "role": "competition_lift" if lift else ("variation" if variation else "accessory"),
                "lift": lift or variation, "fatigue_category": (entry or {}).get("fatigue_category"),
                "load_modes": set(), "weeks": set(), "sets_total": 0.0,
            })
            summary["load_modes"].add(mode)
            summary["weeks"].add(week)
            summary["sets_total"] += sets

    if not weeks:
        return {"weeks": 0}

    baseline = {dimension: weeks[min(weeks)]["fatigue"][dimension] or None for dimension in FATIGUE_DIMENSIONS}
    weekly = []
    for week in sorted(weeks):
        bucket = weeks[week]
        weeks_out = length - week
        row = {
            "week": week,
            "weeks_before_final_week": weeks_out,
            "phase": _phase_for(week, phases),
            "training_days": len(bucket["days"]),
            "total_sets": _round(bucket["sets"]),
            "specificity_narrow": _round(bucket["narrow"] / bucket["sets"], 3) if bucket["sets"] else None,
            "specificity_broad": _round(bucket["broad"] / bucket["sets"], 3) if bucket["sets"] else None,
            "fatigue_vs_week_1": {
                dimension: _round(bucket["fatigue"][dimension] / baseline[dimension], 2) if baseline[dimension] else None
                for dimension in FATIGUE_DIMENSIONS
            },
            "main_lifts": {
                lift: {
                    "top_set_kg": stats["top_kg"] or None,
                    "top_set_pct_of_current_max": _round(stats["top_kg"] / maxes[lift] * 100) if stats["top_kg"] and maxes.get(lift) else None,
                    "sets": _round(stats["sets"]),
                    "reps": _round(stats["reps"]),
                }
                for lift, stats in sorted(bucket["lifts"].items())
            },
        }
        if specificity_band:
            band = specificity_band(weeks_out)
            if band:
                row["expected_specificity_band"] = {"narrow": band.get("narrow"), "broad": band.get("broad")}
        weekly.append(row)

    by_phase: dict[str, list[int]] = defaultdict(list)
    for week in sorted(weeks):
        by_phase[_phase_for(week, phases) or "unphased"].append(week)
    muscle_sets_per_week = {}
    for phase_name, phase_weeks in by_phase.items():
        totals: dict[str, float] = defaultdict(float)
        for week in phase_weeks:
            for muscle, value in weeks[week]["muscles"].items():
                totals[muscle] += value
        muscle_sets_per_week[phase_name] = {muscle: _round(value / len(phase_weeks), 2) for muscle, value in sorted(totals.items(), key=lambda item: -item[1])}

    return {
        "weeks": length,
        "phases": [{"name": phase.get("name"), "weeks": f"{phase.get('week_start')}-{phase.get('week_end')}", "intent": phase.get("intent")} for phase in phases],
        "weekly": weekly,
        "avg_weighted_sets_per_muscle_per_week": muscle_sets_per_week,
        "exercises": {
            name: {**summary, "load_modes": sorted(summary["load_modes"]), "weeks": f"{min(summary['weeks'])}-{max(summary['weeks'])}", "sets_total": _round(summary["sets_total"])}
            for name, summary in exercises.items()
        },
        "notes": [
            "Muscle sets weight primary 1, secondary 0.5, tertiary 0.25, matching the app's workload map.",
            "Fatigue is sets x glossary fatigue profile x relative intensity, shown relative to week 1.",
            f"Exercises without a prescribed load are user-selected and counted at RPE {USER_SELECTED_RPE}.",
            "Specificity narrow = competition-lift sets / all sets; broad also counts same-category variations.",
        ],
    }


def strip_calendar(template: dict) -> dict:
    sessions = [{key: value for key, value in session.items() if key not in ("date", "id")} for session in template.get("sessions") or []]
    meta = {key: value for key, value in (template.get("meta") or {}).items() if key in ("name", "program_context", "estimated_weeks", "days_per_week")}
    return {"meta": meta, "phases": template.get("phases") or [], "sessions": sessions}
