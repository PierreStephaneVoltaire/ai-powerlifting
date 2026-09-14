from __future__ import annotations

import asyncio

from .._video_store import context, get_health_table, get_session_store, resolve_pk, session_for_date, strip_none


async def video_update_metadata(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""

    def update():
        program_sk, phases = context(health_table, pk, version)
        session = session_for_date(store, program_sk, phases, session_date)
        videos = list(session.get("videos") or [])
        index = next((i for i, item in enumerate(videos) if item.get("video_id") == video_id), None)
        if index is None:
            raise ValueError(f"Video {video_id} not found")
        video = dict(videos[index])
        for key, value in (("exercise_name", args.get("exercise_name")), ("set_number", args.get("set_number")), ("notes", args.get("notes"))):
            if value is not None:
                video[key] = value or None
        videos[index] = video
        store.patch_session_sync(program_sk, session_date, {"videos": videos}, phases)
        return strip_none(video)

    return await asyncio.to_thread(update)
