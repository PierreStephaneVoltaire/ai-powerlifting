from __future__ import annotations

import asyncio
from decimal import Decimal

from .._video_store import context, get_health_table, get_session_store, resolve_pk, sort_items, strip_none


def _sanitize_decimals(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, dict):
        return {key: _sanitize_decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_decimals(item) for item in value]
    return value


async def video_library_get(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    exercise = args.get("exercise")
    sort = args.get("sort") or "newest"

    def read():
        program_sk, phases = context(health_table, pk, version)
        items = []
        exercises = set()
        for session in store.list_sessions_sync(program_sk, phases):
            for video in session.get("videos") or []:
                if exercise and video.get("exercise_name") != exercise:
                    continue
                match = None
                exercise_name = video.get("exercise_name")
                if exercise_name:
                    same_name = [item for item in session.get("exercises") or [] if item.get("name") == exercise_name]
                    set_number = video.get("set_number") if isinstance(video.get("set_number"), (int, float)) else None
                    cumulative = 0
                    for candidate in same_name:
                        end = cumulative + max(0, round(float(candidate.get("sets") or 0)))
                        if set_number is not None and cumulative + 1 <= set_number <= end:
                            match = candidate
                            break
                        cumulative = end
                    if match is None and same_name:
                        match = same_name[0]
                    exercises.add(exercise_name)
                items.append({
                    "video": video,
                    "athlete_pk": pk,
                    "session_date": session.get("date"),
                    "session_id": session.get("id") or session.get("session_id"),
                    "day": session.get("day"),
                    "week_number": session.get("week_number"),
                    "phase_name": (session.get("phase") or {}).get("name", ""),
                    "exercise_sets": match.get("sets") if match else 0,
                    "exercise_reps": match.get("reps") if match else 0,
                    "exercise_kg": match.get("kg") if match else None,
                })
        result = {"videos": [strip_none(item) for item in sort_items(items, sort)], "exercises": sorted(exercises)}
        return _sanitize_decimals(result)

    return await asyncio.to_thread(read)
