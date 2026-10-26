from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from services.lib import media_notifications

MEDIA_SK_PREFIX = "Media#"


def get_health_table():
    return dynamodb_resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(
        os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
    )


def get_session_store(args: dict):
    from services.lib.session_store import SessionStore

    pk = args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")
    return SessionStore(
        table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
        pk=pk,
        region=os.environ.get("AWS_REGION", "ca-central-1"),
        source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
    )


def get_s3():
    return aws_client("s3", region_name=os.environ.get("AWS_REGION", "ca-central-1"))


def notify_media_ready(media: dict) -> bool:
    notification = media_notifications.media_ready_notification(media)
    if notification is None:
        return False
    person, event_id, kind, payload = notification
    table = dynamodb_resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(
        media_notifications.notification_table_name()
    )
    try:
        table.meta.client.transact_write_items(
            TransactItems=media_notifications.notification_transaction_items(person, event_id, kind, payload)
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "TransactionCanceledException":
            raise
        if table.get_item(Key=media_notifications.notification_marker_key(event_id), ConsistentRead=True).get("Item"):
            return False
        raise
    return True


def video_extension(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", filename.rsplit(".", 1)[-1] if "." in filename else "mp4") or "mp4"


def resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def resolve_program_sk(health_table: Any, pk: str, version: str) -> str:
    if version == "current":
        pointer = health_table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


def load_phases(health_table: Any, pk: str, program_sk: str):
    response = health_table.get_item(Key={"pk": pk, "sk": program_sk}, ProjectionExpression="phases")
    item = response.get("Item")
    return None if item is None else item.get("phases") or []


def context(health_table: Any, pk: str, version: str):
    program_sk = resolve_program_sk(health_table, pk, version)
    phases = load_phases(health_table, pk, program_sk)
    if phases is None:
        raise ValueError(f"Program version {version} not found")
    return program_sk, phases


def session_for_date(store: Any, program_sk: str, phases: list[dict], session_date: str, session_id: str | None = None):
    matches = [item for item in store.list_sessions_sync(program_sk, phases) if str(item.get("date") or "") == session_date]
    if session_id:
        session = next((item for item in matches if str(item.get("id") or item.get("session_id") or "") == session_id), None)
    elif len(matches) == 1:
        session = matches[0]
    else:
        session = None
    if session is None and len(matches) > 1 and not session_id:
        raise ValueError(f"Multiple sessions with date {session_date}; session_id is required")
    if session is None:
        raise ValueError(f"Session with date {session_date} not found")
    return session


def strip_none(value):
    if isinstance(value, dict):
        return {key: strip_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [strip_none(item) for item in value]
    return value


def safe_number(value) -> float:
    return value if isinstance(value, (int, float)) and value == value else 0


def video_volume(item: dict) -> float:
    sets = safe_number(item.get("exercise_sets"))
    reps = safe_number(item.get("exercise_reps"))
    kg = safe_number(item.get("exercise_kg"))
    return sets * reps * kg if kg > 0 else sets * reps


def sort_items(items: list[dict], sort: str) -> list[dict]:
    if sort == "oldest":
        return sorted(items, key=lambda item: (str(item.get("session_date") or ""), str((item.get("video") or {}).get("uploaded_at") or "")))
    if sort == "volume":
        return sorted(items, key=lambda item: (video_volume(item), safe_number(item.get("exercise_kg")), str(item.get("session_date") or "")), reverse=True)
    if sort == "weight":
        return sorted(items, key=lambda item: (safe_number(item.get("exercise_kg")), str(item.get("session_date") or "")), reverse=True)
    return sorted(items, key=lambda item: (str(item.get("session_date") or ""), str((item.get("video") or {}).get("uploaded_at") or "")), reverse=True)


def cas_update_videos(store: Any, program_sk: str, session_date: str, phases: list[dict], update, session_id: str | None = None) -> dict:
    table = getattr(store, "table", None)
    if table is None:
        sessions = [item for item in store.list_sessions_sync(program_sk, phases) if str(item.get("date") or "") == session_date]
        session = session_for_date(store, program_sk, phases, session_date, session_id)
        videos = update(list(session.get("videos") or []))
        index = sessions.index(session)
        try:
            return store.patch_session_sync(program_sk, session_date, {"videos": videos}, phases, index, media_update=True)
        except TypeError:
            return store.patch_session_sync(program_sk, session_date, {"videos": videos}, phases)

    prefix = f"session#{program_sk}#{session_date}#"
    for _ in range(5):
        kwargs = {"KeyConditionExpression": Key("pk").eq(store._pk) & Key("sk").begins_with(prefix)}
        items = []
        while True:
            response = table.query(**kwargs)
            items.extend(response.get("Items", []))
            if not response.get("LastEvaluatedKey"):
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        if not items:
            raise ValueError(f"Session with date {session_date} not found")
        if session_id:
            item = next((candidate for candidate in items if str(candidate.get("session_id") or candidate.get("id") or "") == session_id), None)
            if item is None:
                raise ValueError(f"Session {session_id} with date {session_date} not found")
        elif len(items) == 1:
            item = items[0]
        else:
            raise ValueError(f"Multiple sessions with date {session_date}; session_id is required")
        videos = update(list(item.get("videos") or []))
        revision = int(item.get("media_revision", 0))
        values = {":videos": videos, ":next": revision + 1, ":revision": revision}
        try:
            table.update_item(
                Key={"pk": item["pk"], "sk": item["sk"]},
                UpdateExpression="SET videos = :videos, media_revision = :next",
                ConditionExpression="attribute_not_exists(media_revision) OR media_revision = :revision",
                ExpressionAttributeValues=values,
            )
            return {**item, "videos": videos, "media_revision": revision + 1}
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    raise ValueError("Concurrent video update conflict")


def media_key(video_id: str) -> str:
    return f"{MEDIA_SK_PREFIX}{video_id}"


def get_media(table: Any, pk: str, video_id: str) -> dict | None:
    item = table.get_item(Key={"pk": pk, "sk": media_key(video_id)}, ConsistentRead=True).get("Item") or None
    if not item or str(item.get("media_id") or item.get("video_id") or "") != video_id:
        return None
    return item


def media_metadata(item: dict) -> dict[str, str]:
    metadata = {
        "video_id": str(item["video_id"]),
        "media_id": str(item["media_id"]),
        "session_date": str(item["session_date"]),
        "session_id": str(item["session_id"]),
        "pk": str(item["pk"]),
        "sk": str(item["program_sk"]),
        "allocation_revision": str(item["allocation_revision"]),
        **({"expected_size": str(item["expected_size"])} if item.get("expected_size") is not None else {}),
    }
    for key in ("lift", "angle", "target_revision"):
        if item.get(key) is not None:
            metadata[key] = str(item[key])
    return metadata


def reserve_lift_profile_slot(table: Any, pk: str, program_sk: str, lift: str, angle: str, video_id: str, s3_key: str, uploaded_at: str, idempotency_key: str = "", source_filename: str = "", source_size: int | None = None) -> int:
    for _ in range(5):
        program = table.get_item(Key={"pk": pk, "sk": program_sk}, ConsistentRead=True).get("Item")
        if not program:
            raise ValueError("Program version not found")
        profiles = [dict(profile) for profile in program.get("lift_profiles") or []]
        profile = next((item for item in profiles if item.get("lift") == lift), None)
        if profile is None:
            profile = {"lift": lift, "style_notes": "", "sticking_points": "", "primary_muscle": "", "volume_tolerance": "moderate"}
            profiles.append(profile)
        videos = dict(profile.get("form_videos") or {})
        current = dict(videos.get(angle) or {})
        pending_id = str(current.get("pending_media_id") or "")
        if pending_id == video_id:
            target_revision = int(current.get("target_revision") or 1)
        elif str(current.get("video_id") or "") == video_id:
            target_revision = int(current.get("target_revision") or 1)
        else:
            target_revision = int(current.get("target_revision") or 0) + 1
        current.update({
            "video_id": current.get("video_id") or video_id,
            "s3_key": current.get("s3_key") or s3_key,
            "uploaded_at": current.get("uploaded_at") or uploaded_at,
            "lift": lift,
            "angle": angle,
            "pending_media_id": video_id,
            "pending_s3_key": s3_key,
            "target_revision": target_revision,
            "processing_status": "pending",
            "thumbnail_status": "pending",
        })
        if idempotency_key:
            current["idempotency_key"] = idempotency_key
        if source_filename:
            current["source_filename"] = source_filename
        if source_size is not None:
            current["source_size"] = source_size
        videos[angle] = current
        profile["form_videos"] = videos
        if profile not in profiles:
            profiles.append(profile)
        try:
            condition = "lift_profiles = :current"
            values = {":current": program.get("lift_profiles") or [], ":next": profiles}
            if program.get("lift_profiles") is None:
                condition = "attribute_not_exists(lift_profiles)"
                values.pop(":current")
            table.update_item(
                Key={"pk": pk, "sk": program_sk},
                UpdateExpression="SET lift_profiles = :next",
                ConditionExpression=condition,
                ExpressionAttributeValues=values,
            )
            return target_revision
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    raise ValueError("Lift profile video reservation conflicted")


def lift_profile_slot(table: Any, pk: str, program_sk: str, lift: str, angle: str) -> dict | None:
    program = table.get_item(Key={"pk": pk, "sk": program_sk}, ConsistentRead=True).get("Item") or {}
    profile = next((item for item in program.get("lift_profiles") or [] if item.get("lift") == lift), None)
    slot = (profile or {}).get("form_videos", {}).get(angle)
    return dict(slot) if isinstance(slot, dict) else None


def allocate_media(table: Any, item: dict) -> dict:
    current = get_media(table, item["pk"], item["video_id"])
    if current:
        if any(str(current.get(key) or "") != str(item.get(key) or "") for key in ("pk", "session_id", "session_date", "program_sk", "lift", "angle")):
            raise ValueError("Video ID is already owned by another session")
        if current.get("status") == "failed":
            item = {
                **current,
                **item,
                "allocation_revision": int(current.get("allocation_revision", 0)) + 1,
                "status": "allocated",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for key in ("processed_s3_key", "thumbnail_s3_key", "source_size", "completed_at", "failure"):
                item.pop(key, None)
            try:
                table.put_item(Item=item, ConditionExpression="allocation_revision = :revision AND #status = :status", ExpressionAttributeNames={"#status": "status"}, ExpressionAttributeValues={":revision": current.get("allocation_revision", 0), ":status": current.get("status")})
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                return get_media(table, item["pk"], item["video_id"]) or item
            return item
        return current
    item.setdefault("allocated_at", datetime.now(timezone.utc).isoformat())
    table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return item
