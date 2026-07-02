from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

_health_table = None
_session_store = None


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


async def video_update_thumbnail(args: dict) -> dict:
    """Update a video's thumbnail s3 key and status.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              required `session_date`, `video_id`, `thumbnail_s3_key`, and
              `status` ('ready' | 'failed').
    """
    health_table = _get_health_table()
    store = _get_session_store()
    pk = _resolve_pk(args)
    store.pk = pk
    version = args.get("version") or "current"
    session_date = args.get("session_date") or ""
    video_id = args.get("video_id") or ""
    thumbnail_s3_key = args.get("thumbnail_s3_key") or ""
    status = args.get("status") or "ready"

    def _sync():
        sk = _resolve_program_sk_sync(health_table, pk, version)
        phases = _load_phases_sync(health_table, pk, sk)
        if phases is None:
            raise ValueError(f"Program version {version} not found")
        sessions = store.list_sessions_sync(sk, phases)
        session = next((s for s in sessions if s.get("date") == session_date), None)
        if not session:
            raise ValueError(f"Session with date {session_date} not found")
        videos = list(session.get("videos") or [])
        idx = next((i for i, v in enumerate(videos) if v.get("video_id") == video_id), None)
        if idx is None:
            raise ValueError(f"Video {video_id} not found")
        videos[idx] = {**videos[idx], "thumbnail_s3_key": thumbnail_s3_key, "thumbnail_status": status}
        store.patch_session_sync(sk, session_date, {"videos": videos}, phases)
        return {"video_id": video_id, "thumbnail_s3_key": thumbnail_s3_key, "thumbnail_status": status}

    return await asyncio.get_running_loop().run_in_executor(None, _sync)