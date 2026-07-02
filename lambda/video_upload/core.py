from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

_health_table = None
_session_store = None
_s3 = None


def _get_health_table():
    global _health_table
    if _health_table is None:
        _health_table = boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")
        ).Table(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))
    return _health_table


def _get_session_store():
    global _session_store
    if _session_store is None:
        from session_store import SessionStore as _SS
        _session_store = _SS(
            table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
            source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        )
    return _session_store


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ca-central-1"))
    return _s3


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _resolve_program_sk_sync(health_table, pk: str, version: str) -> str:
    if version == "current":
        pointer = health_table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


def _load_phases_sync(health_table, pk: str, sk: str):
    resp = health_table.get_item(Key={"pk": pk, "sk": sk}, ProjectionExpression="phases")
    if not resp.get("Item"):
        return None
    return resp["Item"].get("phases") or []


async def video_upload(args: dict) -> dict:
    """Upload a session video to S3 and attach it to a session.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              required `session_date`, `file_b64` (base64 bytes), `filename`,
              `mimetype`, and optional `exercise_name`, `set_number`, `notes`.
    """
    health_table = _get_health_table()
    store = _get_session_store()
    s3 = _get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    pk = _resolve_pk(args)
    store.pk = pk
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    file_b64 = args.get("file_b64") or ""
    filename = args.get("filename") or "video.mp4"
    mimetype = args.get("mimetype") or "video/mp4"
    exercise_name = args.get("exercise_name")
    set_number = args.get("set_number")
    notes = args.get("notes")

    def _sync():
        sk = _resolve_program_sk_sync(health_table, pk, version)
        phases = _load_phases_sync(health_table, pk, sk)
        if phases is None:
            raise ValueError(f"Program version {version} not found")
        sessions = store.list_sessions_sync(sk, phases)
        session = next((s for s in sessions if s.get("date") == session_date), None)
        if not session:
            raise ValueError(f"Session with date {session_date} not found")
        video_id = str(uuid.uuid4())
        extension = (filename.split(".")[-1] if "." in filename else "mp4") or "mp4"
        s3_key = f"videos/{session_date}/{video_id}.{extension}"
        body = base64.b64decode(file_b64) if file_b64 else b""
        if not body:
            raise ValueError("No video bytes provided")
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=body,
            ContentType=mimetype,
            Metadata={"video_id": video_id, "session_date": session_date, "pk": pk, "sk": sk},
        )
        video = {
            "video_id": video_id,
            "s3_key": s3_key,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "thumbnail_status": "pending",
        }
        if exercise_name is not None:
            video["exercise_name"] = exercise_name
        if set_number is not None:
            video["set_number"] = set_number
        if notes is not None:
            video["notes"] = notes
        videos = list(session.get("videos") or []) + [video]
        store.patch_session_sync(sk, session_date, {"videos": videos}, phases)
        return video

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return result