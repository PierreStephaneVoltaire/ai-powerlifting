from __future__ import annotations

import asyncio
import base64
import os
import uuid
from datetime import datetime, timezone

from .._video_store import context, get_health_table, get_s3, get_session_store, resolve_pk, session_for_date, video_extension

MAX_VIDEO_BYTES = 500 * 1024 * 1024


async def video_upload(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    s3 = get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    file_b64 = args.get("file_b64") or ""
    filename = args.get("filename") or "video.mp4"
    mimetype = args.get("mimetype") or "video/mp4"

    def upload():
        program_sk, phases = context(health_table, pk, version)
        session = session_for_date(store, program_sk, phases, session_date)
        body = base64.b64decode(file_b64)
        if not body:
            raise ValueError("No video bytes provided")
        if len(body) > MAX_VIDEO_BYTES:
            raise ValueError("Video exceeds the 500 MB limit")
        video_id = str(uuid.uuid4())
        extension = video_extension(filename)
        s3_key = f"videos/{session_date}/{video_id}.{extension}"
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=body,
            ContentType=mimetype,
            Metadata={"video_id": video_id, "session_date": session_date, "pk": pk, "sk": program_sk},
        )
        video = {"video_id": video_id, "s3_key": s3_key, "uploaded_at": datetime.now(timezone.utc).isoformat(), "thumbnail_status": "pending"}
        for key in ("exercise_name", "set_number", "notes"):
            if args.get(key) is not None:
                video[key] = args[key]
        store.patch_session_sync(program_sk, session_date, {"videos": list(session.get("videos") or []) + [video]}, phases)
        return video

    return await asyncio.to_thread(upload)
