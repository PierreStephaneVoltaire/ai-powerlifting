from __future__ import annotations

from decimal import Decimal
from typing import Optional


ROLE_VALUES = ("athlete", "coach", "handler")
SEX_VALUES = ("male", "female")


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        v = float(value)
        return v if v > 0 else None
    return None


def _normalize_role(value) -> Optional[str]:
    return value if value in ROLE_VALUES else None


def _normalize_roles(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for item in raw:
        role = _normalize_role(item)
        if role and role not in seen:
            seen.append(role)
    return seen


def _normalize_training_maxes(raw) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    squat = _to_float(raw.get("squat_kg"))
    bench = _to_float(raw.get("bench_kg"))
    deadlift = _to_float(raw.get("deadlift_kg"))
    if squat is None or bench is None or deadlift is None:
        return None
    return {"squat_kg": squat, "bench_kg": bench, "deadlift_kg": deadlift}


def _normalize_federations(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for item in raw:
        if isinstance(item, str):
            v = item.strip()
            if v and v not in seen:
                seen.append(v)
    return seen


def onboarding_state_for(settings: dict) -> dict:
    roles = _normalize_roles(settings.get("roles"))
    active_role = _normalize_role(settings.get("active_role"))
    if not active_role and roles:
        active_role = roles[0]
    if not active_role:
        active_role = "athlete"
    return {
        "roles": roles,
        "active_role": active_role,
        "athlete_basics_complete": bool(settings.get("athlete_basics_complete")),
        "profile_complete": bool(settings.get("profile_complete")),
    }


def derive_onboarding_status(settings: dict) -> dict:
    state = onboarding_state_for(settings)
    has_athlete_basics = (
        _to_float(settings.get("bodyweight_kg")) is not None
        and _normalize_training_maxes(settings.get("training_maxes")) is not None
        and settings.get("sex") in SEX_VALUES
    )
    if not state["roles"]:
        next_step = "role"
    elif not state["profile_complete"]:
        next_step = "profile"
    elif "athlete" in state["roles"] and not has_athlete_basics:
        next_step = "athlete_basics"
    else:
        next_step = "done"
    is_onboarded = next_step == "done"
    return {
        "is_onboarded": is_onboarded,
        "next_step": next_step,
        "state": state,
        "has_athlete_basics": has_athlete_basics,
    }


def extend_settings_with_onboarding(settings: dict) -> dict:
    """Return a copy of the settings dict with the onboarding fields filled in.

    Safe to call on legacy rows that have none of the new fields. Also
    coerces floats to Decimal via _to_dynamo on the caller side, so we keep
    values as plain floats here.
    """
    out = dict(settings)
    out["sex"] = settings.get("sex") if settings.get("sex") in SEX_VALUES else None
    bw = _to_float(settings.get("bodyweight_kg"))
    out["bodyweight_kg"] = bw
    out["training_maxes"] = _normalize_training_maxes(settings.get("training_maxes"))
    out["federations"] = _normalize_federations(settings.get("federations"))
    state = onboarding_state_for(settings)
    out["roles"] = state["roles"]
    out["active_role"] = state["active_role"]
    out["athlete_basics_complete"] = state["athlete_basics_complete"]
    out["profile_complete"] = state["profile_complete"]
    return out
