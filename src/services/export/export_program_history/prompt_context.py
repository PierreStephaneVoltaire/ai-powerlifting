from __future__ import annotations

from typing import Any

from services.runtime.lift_profiles import describe as describe_lift_profile


def summarize_lift_profiles(lift_profiles: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not lift_profiles:
        return []
    ordered: list[dict[str, Any]] = []
    for lift in ("squat", "bench", "deadlift"):
        profile = next((p for p in lift_profiles if p.get("lift") == lift), None)
        if not profile:
            continue
        ordered.append({
            "lift": profile.get("lift"),
            "technique": describe_lift_profile(profile)["technique"],
            "notes": profile.get("notes") or "",
            "volume_tolerance": profile.get("volume_tolerance") or "moderate",
            "e1rm_multiplier": profile.get("e1rm_multiplier", 1.0),
            "stimulus_coefficient": profile.get("stimulus_coefficient", 1.0),
        })
    return ordered
