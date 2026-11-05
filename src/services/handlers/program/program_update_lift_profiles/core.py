from __future__ import annotations
from services.lib.program_tool_helpers import get_store

LIFTS = {"squat", "bench", "deadlift"}
ANGLES = {"front", "side", "diagonal"}


def _profile(profile):
    from services.lib.lift_profiles import clean
    result = clean(profile)
    if result is None:
        return None
    videos = profile.get("form_videos")
    if isinstance(videos, dict):
        result["form_videos"] = {
            angle: dict(video)
            for angle, video in videos.items()
            if angle in ANGLES and isinstance(video, dict)
        }
    return result


def normalize_lift_profiles(profiles):
    normalized = []
    for profile in profiles if isinstance(profiles, list) else []:
        value = _profile(profile)
        if value is not None:
            normalized.append(value)
    return normalized


async def program_update_lift_profiles(args: dict):
    store = get_store(args)
    profiles = args.get("lift_profiles") or args.get("profiles") or []
    current = await store.get_program()
    current_by_lift = {
        profile.get("lift"): profile.get("form_videos")
        for profile in current.get("lift_profiles") or []
        if profile.get("lift") in LIFTS
    }
    normalized = normalize_lift_profiles(profiles)
    for profile in normalized:
        if profile.get("lift") in current_by_lift:
            profile["form_videos"] = current_by_lift[profile["lift"]]
        else:
            profile.pop("form_videos", None)
    return await store.update_lift_profiles(normalized)
