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


def _strip_undefined(obj):
    if obj is None or not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if v is None:
            continue
        out[k] = _strip_undefined(v) if isinstance(v, dict) else v
    return out


def _safe_number(value) -> float:
    return value if isinstance(value, (int, float)) and value == value else 0


def _video_volume_kg(item: dict) -> float:
    sets = _safe_number(item.get("exercise_sets"))
    reps = _safe_number(item.get("exercise_reps"))
    kg = _safe_number(item.get("exercise_kg"))
    if kg > 0:
        return sets * reps * kg
    return sets * reps


def _sort_items(items: list[dict], sort: str) -> list[dict]:
    if sort == "oldest":
        return sorted(items, key=lambda it: (str(it.get("session_date") or ""), str((it.get("video") or {}).get("uploaded_at") or "")))
    if sort == "volume":
        return sorted(items, key=lambda it: (_video_volume_kg(it), _safe_number(it.get("exercise_kg")), str(it.get("session_date") or "")), reverse=True)
    if sort == "weight":
        return sorted(items, key=lambda it: (_safe_number(it.get("exercise_kg")), str(it.get("session_date") or "")), reverse=True)
    return sorted(items, key=lambda it: (str(it.get("session_date") or ""), str((it.get("video") or {}).get("uploaded_at") or "")), reverse=True)


async def video_library_get(args: dict) -> dict:
    """Get the video library across sessions, optionally filtered by exercise.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              `exercise` (filter by exercise_name), and `sort`
              ('newest'|'oldest'|'volume'|'weight', defaults to 'newest').
    """
    health_table = _get_health_table()
    store = _get_session_store()
    pk = _resolve_pk(args)
    store.pk = pk
    version = args.get("version") or "current"
    exercise = args.get("exercise")
    sort = args.get("sort") or "newest"

    def _sync():
        sk = _resolve_program_sk_sync(health_table, pk, version)
        phases = _load_phases_sync(health_table, pk, sk)
        if phases is None:
            return {"videos": [], "exercises": []}
        sessions = store.list_sessions_sync(sk, phases)
        items = []
        exercise_set = set()
        for session in sessions:
            videos = session.get("videos") or []
            if not videos:
                continue
            for video in videos:
                if exercise and video.get("exercise_name") != exercise:
                    continue
                match = None
                ex_name = video.get("exercise_name")
                if ex_name:
                    same_name = [e for e in (session.get("exercises") or []) if e.get("name") == ex_name]
                    set_number = video.get("set_number") if isinstance(video.get("set_number"), (int, float)) else None
                    if set_number is not None and same_name:
                        cumulative = 0
                        for candidate in same_name:
                            set_count = max(0, round(float(candidate.get("sets") or 0)))
                            start = cumulative + 1
                            end = cumulative + set_count
                            if start <= set_number <= end:
                                match = candidate
                                break
                            cumulative = end
                    if not match and same_name:
                        match = same_name[0]
                if ex_name:
                    exercise_set.add(ex_name)
                items.append({
                    "video": video,
                    "session_date": session.get("date"),
                    "day": session.get("day"),
                    "week_number": session.get("week_number"),
                    "phase_name": (session.get("phase") or {}).get("name", ""),
                    "exercise_sets": match.get("sets") if match else 0,
                    "exercise_reps": match.get("reps") if match else 0,
                    "exercise_kg": match.get("kg") if match else None,
                })
        items = _sort_items(items, sort)
        return {
            "videos": [_strip_undefined(it) for it in items],
            "exercises": sorted(exercise_set),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _sync)