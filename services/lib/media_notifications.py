from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def _dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _dynamo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dynamo(item) for item in value]
    return value


def notification_table_name() -> str:
    return os.getenv("IF_POWERLIFTING_NOTIFICATIONS_TABLE", "if-powerlifting-notifications")


def notification_marker_key(event_id: str) -> dict[str, str]:
    return {"pk": f"Event#{event_id}", "sk": "Notification"}


def media_ready_notification(media: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]] | None:
    person = str(media.get("uploader_person_pk") or media.get("_person_pk") or "").strip()
    if not person or media.get("status") != "confirmed" or not media.get("processed_s3_key") or not media.get("thumbnail_s3_key"):
        return None
    revision = int(media.get("allocation_revision", 0))
    video_id = str(media.get("video_id") or media.get("media_id") or "").strip()
    pk = str(media.get("pk") or "").strip()
    if not pk or not video_id or revision < 1:
        return None
    event_id = f"video:{pk}:{video_id}:ready:{revision}"
    payload = {
        "video_id": video_id,
        "session_date": str(media.get("session_date") or ""),
        "processed_s3_key": str(media["processed_s3_key"]),
        "thumbnail_s3_key": str(media["thumbnail_s3_key"]),
    }
    for key in ("lift", "angle"):
        if media.get(key) is not None:
            payload[key] = media[key]
    return person, event_id, "video_ready", payload


def notification_transaction_items(
    person: str,
    event_id: str,
    kind: str,
    payload: dict[str, Any],
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    marker = {
        **notification_marker_key(event_id),
        "event_id": event_id,
        "created_at": timestamp,
    }
    item = {
        "pk": f"Person#{person}",
        "sk": f"Notification#{timestamp}#{event_id}",
        "notification_id": event_id,
        "event_id": event_id,
        "kind": kind,
        "payload": payload,
        "read_at": None,
        "created_at": timestamp,
        "gsi1pk": f"Event#{event_id}",
        "gsi1sk": "Notification",
    }
    table_name = notification_table_name()
    return [
        {"Put": {"TableName": table_name, "Item": _dynamo(marker), "ConditionExpression": "attribute_not_exists(pk)"}},
        {"Put": {"TableName": table_name, "Item": _dynamo(item), "ConditionExpression": "attribute_not_exists(pk)"}},
    ]
