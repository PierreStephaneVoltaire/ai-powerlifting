import math
import re
import uuid

MUSCLES = frozenset("quads hamstrings glutes calves tibialis_anterior hip_flexors adductors chest triceps front_delts side_delts rear_delts lats traps rhomboids teres_major biceps forearms erectors lower_back core obliques serratus".split())
CATEGORIES = frozenset("squat bench deadlift back chest arm legs core lower_back".split())
EQUIPMENT = frozenset("barbell dumbbell cable machine bodyweight hex_bar bands kettlebell".split())
FATIGUE_CATEGORIES = frozenset("primary_axial primary_upper secondary accessory".split())
FATIGUE_AXES = ("axial", "neural", "peripheral", "systemic")


def compatible_variation(left, right):
    def unilateral(name):
        return bool(re.search(r"\b(?:unilateral|(?:single|one)[ -]?(?:arm|leg))\b", name.casefold()))
    return unilateral(left) == unilateral(right)


def create_missing_exercises(names, proposed, exercises, pk):
    from services.runtime.analytics_client import call

    existing = {str(item.get("name") or "").casefold(): str(item["id"]) for item in exercises if item.get("id")}
    proposals = {str(item.get("name") or "").strip().casefold(): item for item in proposed if isinstance(item, dict)}
    resolved, pending = {}, []
    for name in sorted(names):
        key = name.strip().casefold()
        if key in existing:
            resolved[name] = existing[key]
            continue
        item = proposals.get(key)
        if not item:
            raise ValueError(f"Missing glossary metadata for {name}; retry the import")
        profile = item.get("fatigue_profile")
        if not isinstance(profile, dict) or any(
            isinstance(profile.get(axis), bool)
            or not isinstance(profile.get(axis), (int, float))
            or not math.isfinite(profile[axis])
            or not 0 <= profile[axis] <= 1
            for axis in FATIGUE_AXES
        ):
            raise ValueError(f"Invalid fatigue profile for {name}")
        groups = [item.get(field) for field in ("primary_muscles", "secondary_muscles", "tertiary_muscles")]
        if any(not isinstance(group, list) or any(not isinstance(muscle, str) or muscle not in MUSCLES for muscle in group) for group in groups) or not groups[0]:
            raise ValueError(f"Invalid muscle groups for {name}")
        flattened = [muscle for group in groups for muscle in group]
        if len(flattened) != len(set(flattened)) or any(len(group) > limit for group, limit in zip(groups, (4, 5, 5))):
            raise ValueError(f"Invalid muscle groups for {name}")
        if item.get("category") not in CATEGORIES or item.get("equipment") not in EQUIPMENT or item.get("fatigue_category") not in FATIGUE_CATEGORIES or not isinstance(item.get("fatigue_profile_reasoning"), str) or not item["fatigue_profile_reasoning"].strip():
            raise ValueError(f"Missing glossary metadata for {name}")
        exercise = {field: item[field] for field in ("category", "fatigue_category", "equipment", "primary_muscles", "secondary_muscles", "tertiary_muscles", "fatigue_profile_reasoning")}
        exercise.update({
            "name": name,
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"nolift-import:{pk}:{key}")),
            "fatigue_profile": {axis: profile[axis] for axis in FATIGUE_AXES},
            "fatigue_profile_source": "ai_estimated",
        })
        pending.append((name, exercise))
    for name, exercise in pending:
        result = call("exercise_upsert", {"pk": pk, "exercise": exercise}, athlete=pk, domain="glossary")
        if not result.get("id"):
            raise ValueError(f"Glossary did not return an ID for {name}")
        resolved[name] = str(result["id"])
    return resolved
