from __future__ import annotations

import asyncio

from .._video_store import context, get_health_table, get_session_store, resolve_pk, sort_items, strip_none


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
                    "session_date": session.get("date"),
                    "day": session.get("day"),
                    "week_number": session.get("week_number"),
                    "phase_name": (session.get("phase") or {}).get("name", ""),
                    "exercise_sets": match.get("sets") if match else 0,
                    "exercise_reps": match.get("reps") if match else 0,
                    "exercise_kg": match.get("kg") if match else None,
                })
        return {"videos": [strip_none(item) for item in sort_items(items, sort)], "exercises": sorted(exercises)}

    return await asyncio.to_thread(read)
