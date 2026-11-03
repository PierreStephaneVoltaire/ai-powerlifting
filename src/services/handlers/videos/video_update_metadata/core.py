from __future__ import annotations

import asyncio

from .._video_store import cas_update_videos, context, get_health_table, get_media, get_session_store, resolve_pk, session_for_date, strip_none


async def video_update_metadata(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""
    session_id = str(args.get("session_id") or "").strip() or None

    def update():
        program_sk, phases = context(health_table, pk, version)
        media = get_media(health_table, pk, video_id)
        if not media:
            raise ValueError("Video allocation not found")
        if media.get("readonly"):
            raise ValueError("Video is read-only")
        if str(media.get("program_sk")) != program_sk or str(media.get("session_date")) != session_date or (session_id and str(media.get("session_id")) != session_id):
            raise ValueError("Video does not belong to the requested session")
        resolved_session_id = session_id or str(media.get("session_id"))
        session = session_for_date(store, program_sk, phases, session_date, resolved_session_id)
        result = None
        def update(videos):
            nonlocal result
            index = next((i for i, item in enumerate(videos) if item.get("video_id") == video_id), None)
            if index is None:
                raise ValueError(f"Video {video_id} not found")
            video = dict(videos[index])
            for key, value in (("exercise_name", args.get("exercise_name")), ("set_number", args.get("set_number")), ("notes", args.get("notes"))):
                if value is not None:
                    video[key] = value or None
            videos[index] = video
            result = video
            return videos
        cas_update_videos(store, program_sk, session_date, phases, update, str(session.get("id") or session.get("session_id") or resolved_session_id or "") or None)
        return strip_none(result or {})

    return await asyncio.to_thread(update)
