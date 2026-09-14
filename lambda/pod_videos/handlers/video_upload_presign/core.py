from __future__ import annotations

import asyncio
import os
import uuid

from .._video_store import context, get_health_table, get_s3, get_session_store, resolve_pk, session_for_date, video_extension

UPLOAD_EXPIRY_SECONDS = 900


async def video_upload_presign(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    s3 = get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    filename = args.get("filename") or "video.mp4"
    mimetype = args.get("mimetype") or "video/mp4"

    def presign():
        program_sk, phases = context(health_table, pk, version)
        session_for_date(store, program_sk, phases, session_date)
        video_id = str(uuid.uuid4())
        s3_key = f"videos/{session_date}/{video_id}.{video_extension(filename)}"
        metadata = {"video_id": video_id, "session_date": session_date, "pk": pk, "sk": program_sk}
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": s3_key, "ContentType": mimetype, "Metadata": metadata},
            ExpiresIn=UPLOAD_EXPIRY_SECONDS,
        )
        return {"video_id": video_id, "s3_key": s3_key, "upload_url": upload_url, "upload_headers": {"Content-Type": mimetype, **{f"x-amz-meta-{key}": value for key, value in metadata.items()}}, "expires_in": UPLOAD_EXPIRY_SECONDS}

    return await asyncio.to_thread(presign)
