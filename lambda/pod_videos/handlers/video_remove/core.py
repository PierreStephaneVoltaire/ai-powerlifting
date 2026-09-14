from __future__ import annotations

import asyncio
import logging
import os

from .._video_store import context, get_health_table, get_s3, get_session_store, resolve_pk, session_for_date

logger = logging.getLogger(__name__)


async def video_remove(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    s3 = get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""

    def remove():
        program_sk, phases = context(health_table, pk, version)
        session = session_for_date(store, program_sk, phases, session_date)
        video = next((item for item in session.get("videos") or [] if item.get("video_id") == video_id), None)
        if video is None:
            raise ValueError(f"Video {video_id} not found")
        for key in (video.get("s3_key"), video.get("thumbnail_s3_key")):
            if key:
                try:
                    s3.delete_object(Bucket=bucket, Key=key)
                except Exception as exc:
                    logger.warning("Failed to delete video object: %s", exc)
        remaining = [item for item in session.get("videos") or [] if item.get("video_id") != video_id]
        store.patch_session_sync(program_sk, session_date, {"videos": remaining or None}, phases)
        return {"removed": video_id}

    return await asyncio.to_thread(remove)
