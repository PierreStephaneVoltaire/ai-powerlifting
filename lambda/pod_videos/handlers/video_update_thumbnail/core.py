from __future__ import annotations

import asyncio

from .._video_store import context, get_health_table, get_session_store, resolve_pk, session_for_date


async def video_update_thumbnail(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""
    thumbnail_s3_key = args.get("thumbnail_s3_key") or ""
    status = args.get("status") or "ready"

    def update():
        program_sk, phases = context(health_table, pk, version)
        session = session_for_date(store, program_sk, phases, session_date)
        videos = list(session.get("videos") or [])
        index = next((i for i, item in enumerate(videos) if item.get("video_id") == video_id), None)
        if index is None:
            raise ValueError(f"Video {video_id} not found")
        videos[index] = {**videos[index], "thumbnail_s3_key": thumbnail_s3_key, "thumbnail_status": status}
        store.patch_session_sync(program_sk, session_date, {"videos": videos}, phases)
        return {"video_id": video_id, "thumbnail_s3_key": thumbnail_s3_key, "thumbnail_status": status}

    return await asyncio.to_thread(update)
