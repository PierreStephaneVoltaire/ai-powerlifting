from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from .._video_store import cas_update_videos, context, get_health_table, get_media, get_s3, get_session_store, lift_profile_slot, notify_media_ready, resolve_pk, session_for_date

MAX_VIDEO_BYTES = 500 * 1024 * 1024


async def video_upload_confirm(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    s3 = get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    session_id = str(args.get("session_id") or "").strip() or None
    video_id = args.get("video_id") or ""
    s3_key = args.get("s3_key") or ""
    requested_session_id = str(args.get("session_id") or "").strip() or None
    target_lift = str(args.get("lift") or "").strip() or None
    target_angle = str(args.get("angle") or "").strip() or None

    def confirm():
        program_sk, phases = context(health_table, pk, version)
        table_media = get_media(health_table, pk, video_id)
        if not table_media:
            raise ValueError("Video upload allocation not found")
        if table_media.get("readonly"):
            raise ValueError("Video is read-only")
        if table_media.get("status") in {"failed", "removed", "legacy"}:
            raise ValueError("Video upload must be retried after processing failure")
        if str(table_media.get("program_sk")) != program_sk or str(table_media.get("session_date")) != session_date:
            raise ValueError("Video upload allocation does not match the requested session")
        if requested_session_id and str(table_media.get("session_id")) != requested_session_id:
            raise ValueError("Video upload allocation does not match the requested session")
        session_id = str(table_media.get("session_id") or "")
        if table_media.get("lift") and not target_lift:
            raise ValueError("Form video target is required for its allocation")
        if target_lift:
            if table_media.get("lift") != target_lift or table_media.get("angle") != target_angle:
                raise ValueError("Form video target does not match its allocation")
            slot = lift_profile_slot(health_table, pk, program_sk, target_lift, target_angle)
            published = slot and str(slot.get("video_id") or "") == video_id and not slot.get("pending_media_id")
            pending = slot and str(slot.get("pending_media_id") or "") == video_id
            if not slot or (not published and not pending) or str(slot.get("target_revision") or "") != str(table_media.get("target_revision") or ""):
                raise ValueError("Form video reservation is no longer current")
            session = None
        else:
            session = session_for_date(store, program_sk, phases, session_date, session_id)
        if str(table_media.get("s3_key")) != s3_key:
            raise ValueError("Uploaded video key does not match its allocation")
        completed = table_media.get("status") in {"ready", "confirmed"} and table_media.get("processed_s3_key")
        content_length = int(table_media.get("source_size") or 0)
        metadata = {}
        if not completed:
            try:
                head = s3.head_object(Bucket=bucket, Key=s3_key)
            except Exception:
                raise ValueError("Uploaded video is not available")
            metadata = {str(key).lower(): str(value) for key, value in (head.get("Metadata") or {}).items()}
            expected_metadata = {
                "pk": pk,
                "sk": program_sk,
                "video_id": video_id,
                "session_date": session_date,
            }
            expected_metadata.update({"session_id": session_id, "media_id": video_id, "allocation_revision": str(table_media.get("allocation_revision"))})
            if table_media.get("expected_size") is not None:
                expected_metadata["expected_size"] = str(table_media["expected_size"])
            if any(metadata.get(key) != value for key, value in expected_metadata.items()):
                raise ValueError("Uploaded video metadata does not match the authenticated athlete allocation")
            content_length = int(head.get("ContentLength") or 0)
        if completed:
            content_length = content_length or int(table_media.get("expected_size") or args.get("expected_size") or 1)
        if content_length <= 0:
            raise ValueError("Uploaded video is empty")
        if content_length > MAX_VIDEO_BYTES:
            raise ValueError("Video exceeds the 500 MB limit")
        expected_size = args.get("expected_size")
        if expected_size is None:
            expected_size = table_media.get("expected_size") or metadata.get("expected_size")
        if expected_size is not None and content_length != int(expected_size):
            raise ValueError("Uploaded video size does not match the original file")
        result = None

        if target_lift:
            result = {
                "video_id": video_id,
                "s3_key": table_media.get("processed_s3_key") or s3_key,
                "uploaded_at": str(table_media.get("allocated_at") or datetime.now(timezone.utc).isoformat()),
                "thumbnail_status": "ready" if table_media.get("processed_s3_key") else "pending",
                "lift": target_lift,
                "angle": target_angle,
                "target_revision": int(table_media.get("target_revision", 0)),
                "allocation_revision": int(table_media.get("allocation_revision", 0)),
            }
            for key in ("processed_s3_key", "thumbnail_s3_key", "video_url", "thumbnail_url"):
                if table_media.get(key):
                    result[key] = table_media[key]
            if table_media.get("idempotency_key") or args.get("idempotency_key"):
                result["idempotency_key"] = table_media.get("idempotency_key") or args.get("idempotency_key")

        def update(videos):
            nonlocal result
            existing = next((item for item in videos if item.get("video_id") == video_id), None)
            if existing:
                current_revision = int(existing.get("allocation_revision", 0))
                allocation_revision = int(table_media.get("allocation_revision", 0))
                if current_revision > allocation_revision:
                    raise ValueError("Video allocation is stale")
                if allocation_revision > current_revision:
                    existing = {
                        **existing,
                        "s3_key": s3_key,
                        "thumbnail_status": "pending",
                        "allocation_revision": allocation_revision,
                    }
                    for key in ("processed_s3_key", "thumbnail_s3_key", "video_url", "thumbnail_url"):
                        existing.pop(key, None)
                    for key in ("exercise_name", "set_number", "notes", "lift", "angle", "target_revision"):
                        if args.get(key) is not None:
                            existing[key] = args[key]
                    videos[videos.index(next(item for item in videos if item.get("video_id") == video_id))] = existing
                result = existing
                return videos
            video = {
                "video_id": video_id,
                "s3_key": table_media.get("processed_s3_key") or s3_key,
                "session_id": session_id,
                "uploaded_at": str(table_media.get("allocated_at") or datetime.now(timezone.utc).isoformat()),
                "thumbnail_status": "ready" if table_media.get("processed_s3_key") else "pending",
                "allocation_revision": int(table_media.get("allocation_revision", 0)),
            }
            if table_media.get("idempotency_key") or args.get("idempotency_key"):
                video["idempotency_key"] = table_media.get("idempotency_key") or args.get("idempotency_key")
            for key in ("processed_s3_key", "thumbnail_s3_key", "video_url", "thumbnail_url"):
                if table_media.get(key):
                    video[key] = table_media[key]
            for key in ("exercise_name", "set_number", "notes", "lift", "angle", "target_revision"):
                if args.get(key) is not None:
                    video[key] = args[key]
            result = video
            return videos + [video]
        if not target_lift:
            cas_update_videos(store, program_sk, session_date, phases, update, session_id)
        current = get_media(health_table, pk, video_id)
        if current and current.get("status") != "confirmed":
            try:
                health_table.put_item(
                    Item={**current, "status": "confirmed", "confirmed_at": datetime.now(timezone.utc).isoformat()},
                    ConditionExpression="allocation_revision = :revision AND #status = :status",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={":revision": current.get("allocation_revision", 0), ":status": current.get("status")},
                )
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
        current = get_media(health_table, pk, video_id) or current
        if current:
            notify_media_ready(current)
        return result

    return await asyncio.to_thread(confirm)
