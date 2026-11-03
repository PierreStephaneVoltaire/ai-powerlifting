from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from .._video_store import allocate_media, context, get_health_table, get_session_store, media_metadata, reserve_lift_profile_slot, resolve_pk, session_for_date, video_extension


async def video_upload_presign(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    session_id = str(args.get("session_id") or "").strip() or None
    lift = str(args.get("lift") or "").strip() or None
    angle = str(args.get("angle") or "").strip() or None
    target_revision = args.get("target_revision")
    if bool(lift) != bool(angle) or lift not in {None, "squat", "bench", "deadlift"} or angle not in {None, "front", "side", "diagonal"}:
        raise ValueError("lift and angle must identify a valid form video slot")
    filename = args.get("filename") or "video.mp4"
    mimetype = args.get("mimetype") or "video/mp4"

    def presign():
        program_sk, phases = context(health_table, pk, version)
        resolved_session_id = f"lift-profile:{lift}:{angle}" if lift else ""
        if not lift:
            session = session_for_date(store, program_sk, phases, session_date, session_id)
            resolved_session_id = str(session.get("id") or session.get("session_id") or "")
            if not resolved_session_id:
                raise ValueError("Session has no persisted session_id")
        idempotency_key = str(args.get("idempotency_key") or "").strip()
        video_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"if-video:{pk}:{program_sk}:{resolved_session_id}:{lift or ''}:{angle or ''}:{idempotency_key}")) if idempotency_key else str(uuid.uuid4())
        s3_key = f"videos/{session_date}/{video_id}.{video_extension(filename)}"
        item = {
            "pk": pk,
            "sk": f"Media#{video_id}",
            "entity_type": "media",
            "media_id": video_id,
            "video_id": video_id,
            "session_id": resolved_session_id,
            "session_date": session_date,
            "program_sk": program_sk,
            "s3_key": s3_key,
            "source_s3_key": s3_key,
            "allocation_revision": 1,
            "status": "allocated",
        }
        if lift:
            item.update({"lift": lift, "angle": angle})
        if idempotency_key:
            item["idempotency_key"] = idempotency_key
        if args.get("_person_pk"):
            item["uploader_person_pk"] = str(args["_person_pk"])
        if args.get("expected_size") is not None:
            expected_size = int(args["expected_size"])
            if expected_size <= 0 or expected_size > 500 * 1024 * 1024:
                raise ValueError("Video size must be between 1 byte and 500 MB")
            item["expected_size"] = expected_size
        if lift:
            item["target_revision"] = reserve_lift_profile_slot(
                health_table, pk, program_sk, lift, angle, video_id, s3_key,
                datetime.now(timezone.utc).isoformat(),
                idempotency_key,
                filename,
                item.get("expected_size"),
            )
        item = allocate_media(health_table, item)
        metadata = media_metadata(item)
        return {"video_id": video_id, "s3_key": s3_key, "metadata": metadata}

    return await asyncio.to_thread(presign)
