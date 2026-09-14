from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from .._video_store import context, get_health_table, get_s3, get_session_store, resolve_pk, session_for_date

MAX_VIDEO_BYTES = 500 * 1024 * 1024


async def video_upload_confirm(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    s3 = get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""
    s3_key = args.get("s3_key") or ""

    def confirm():
        program_sk, phases = context(health_table, pk, version)
        session = session_for_date(store, program_sk, phases, session_date)
        expected_prefix = f"videos/{session_date}/{video_id}."
        if not s3_key.startswith(expected_prefix):
            raise ValueError("Uploaded video key does not match the requested session")
        head = s3.head_object(Bucket=bucket, Key=s3_key)
        metadata = {str(key).lower(): str(value) for key, value in (head.get("Metadata") or {}).items()}
        if metadata.get("pk") != pk or metadata.get("sk") != program_sk or metadata.get("video_id") != video_id or metadata.get("session_date") != session_date:
            raise ValueError("Uploaded video metadata does not match the authenticated athlete")
        if int(head.get("ContentLength") or 0) > MAX_VIDEO_BYTES:
            raise ValueError("Video exceeds the 500 MB limit")
        existing = next((item for item in session.get("videos") or [] if item.get("video_id") == video_id), None)
        if existing:
            return existing
        video = {"video_id": video_id, "s3_key": s3_key, "uploaded_at": datetime.now(timezone.utc).isoformat(), "thumbnail_status": "pending"}
        for key in ("exercise_name", "set_number", "notes"):
            if args.get(key) is not None:
                video[key] = args[key]
        store.patch_session_sync(program_sk, session_date, {"videos": list(session.get("videos") or []) + [video]}, phases)
        return video

    return await asyncio.to_thread(confirm)
