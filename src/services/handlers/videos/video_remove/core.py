from __future__ import annotations

import asyncio

from botocore.exceptions import ClientError

from .._video_store import cas_update_videos, context, get_health_table, get_media, get_session_store, resolve_pk, session_for_date


def _remove_lift_profile_video(table, pk: str, program_sk: str, lift: str, angle: str, video_id: str) -> None:
    for _ in range(5):
        program = table.get_item(Key={"pk": pk, "sk": program_sk}, ConsistentRead=True).get("Item") or {}
        profiles = [dict(profile) for profile in program.get("lift_profiles") or []]
        profile = next((item for item in profiles if item.get("lift") == lift), None)
        slot = (profile or {}).get("form_videos", {}).get(angle)
        if not isinstance(slot, dict):
            return
        ready = str(slot.get("video_id") or "") == video_id
        pending = str(slot.get("pending_media_id") or "") == video_id
        if not ready and not pending:
            return
        videos = dict(profile.get("form_videos") or {})
        if pending:
            replacement = dict(slot)
            replacement.pop("pending_media_id", None)
            replacement.pop("pending_s3_key", None)
            replacement.pop("failure", None)
            if slot.get("video_id") and str(slot.get("video_id")) != video_id:
                replacement["processing_status"] = "ready"
                replacement["thumbnail_status"] = "ready"
                videos[angle] = replacement
            else:
                videos.pop(angle, None)
        else:
            if slot.get("pending_media_id"):
                replacement = dict(slot)
                for key in ("video_id", "s3_key", "uploaded_at", "thumbnail_s3_key", "video_url", "thumbnail_url", "allocation_revision"):
                    replacement.pop(key, None)
                videos[angle] = replacement
            else:
                videos.pop(angle, None)
        profile["form_videos"] = videos
        values = {":current": program.get("lift_profiles") or [], ":next": profiles}
        try:
            table.update_item(
                Key={"pk": pk, "sk": program_sk},
                UpdateExpression="SET lift_profiles = :next",
                ConditionExpression="lift_profiles = :current",
                ExpressionAttributeValues=values,
            )
            return
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    raise ValueError("Lift profile video removal conflicted")


async def video_remove(args: dict) -> dict:
    health_table = get_health_table()
    store = get_session_store(args)
    pk = resolve_pk(args)
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""
    requested_session_id = str(args.get("session_id") or "").strip() or None

    def remove():
        program_sk, phases = context(health_table, pk, version)
        media = get_media(health_table, pk, video_id)
        if not media:
            raise ValueError("Video allocation not found")
        if media.get("readonly"):
            raise ValueError("Video is read-only")
        if str(media.get("program_sk")) != program_sk or str(media.get("session_date")) != session_date or (requested_session_id and str(media.get("session_id")) != requested_session_id):
            raise ValueError("Video does not belong to the requested session")
        if media.get("lift") and media.get("angle"):
            for _ in range(5):
                if media.get("status") == "removed":
                    break
                try:
                    health_table.put_item(
                        Item={**media, "status": "removed"},
                        ConditionExpression="allocation_revision = :revision AND #status = :status",
                        ExpressionAttributeNames={"#status": "status"},
                        ExpressionAttributeValues={":revision": media.get("allocation_revision", 0), ":status": media.get("status")},
                    )
                    break
                except ClientError as error:
                    if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                        raise
                    media = get_media(health_table, pk, video_id)
                    if not media:
                        raise ValueError("Video allocation not found")
            else:
                raise ValueError("Video removal conflicted with processing")
            _remove_lift_profile_video(health_table, pk, program_sk, str(media.get("lift")), str(media.get("angle")), video_id)
            return {"removed": video_id}
        session_id = requested_session_id or str(media.get("session_id"))
        session = session_for_date(store, program_sk, phases, session_date, session_id)
        session_id = str(session.get("id") or session.get("session_id") or session_id or "")
        video = next((item for item in session.get("videos") or [] if item.get("video_id") == video_id), None)
        if video is None and media.get("status") == "removed":
            return {"removed": video_id}
        if video is None:
            raise ValueError(f"Video {video_id} not found")
        for _ in range(5):
            if media.get("status") == "removed":
                break
            try:
                health_table.put_item(
                    Item={**media, "status": "removed"},
                    ConditionExpression="allocation_revision = :revision AND #status = :status",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={":revision": media.get("allocation_revision", 0), ":status": media.get("status")},
                )
                break
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                media = get_media(health_table, pk, video_id)
                if not media:
                    raise ValueError("Video allocation not found")
        else:
            raise ValueError("Video removal conflicted with processing")
        cas_update_videos(store, program_sk, session_date, phases, lambda videos: [item for item in videos if item.get("video_id") != video_id] or None, session_id)
        return {"removed": video_id}

    return await asyncio.to_thread(remove)
