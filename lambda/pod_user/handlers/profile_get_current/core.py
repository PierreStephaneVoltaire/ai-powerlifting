from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

_user_table = None
_health_table = None
_session_table = None

NICKNAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")
MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")
AGE_CATEGORY_VALUES = (
    "open",
    "subjunior",
    "junior",
    "master1",
    "master2",
    "master3",
    "master4",
)
DOTS_COEFFICIENTS = {
    "male": {"a": -307.75076, "b": 24.0900756, "c": -0.1918759221, "d": 0.0007391293, "e": -0.000001093},
    "female": {"a": -57.96288, "b": 13.6175032, "c": -0.1126655495, "d": 0.0005158568, "e": -0.0000010706},
}


def _get_user_table():
    global _user_table
    if _user_table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        _user_table = boto3.resource("dynamodb", region_name=region).Table(
            os.environ.get("IF_USER_TABLE", "if-user")
        )
    return _user_table


def _get_health_table():
    global _health_table
    if _health_table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        _health_table = boto3.resource("dynamodb", region_name=region).Table(
            os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
        )
    return _health_table


def _get_session_table():
    global _session_table
    if _session_table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        _session_table = boto3.resource("dynamodb", region_name=region).Table(
            os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions")
        )
    return _session_table


def _sanitize_username(username: str) -> str:
    sanitized = re.sub(r"[^a-z0-9_-]", "_", (username or "").lower())[:32]
    return sanitized if NICKNAME_RE.match(sanitized) else f"user_{int(datetime.now(timezone.utc).timestamp())}"


def _sanitize_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _normalize_settings(raw: dict) -> dict:
    discord_username = str(raw.get("discord_username") or raw.get("username") or "")
    username = _sanitize_username(str(raw.get("username") or discord_username or raw.get("nickname") or "user"))
    nickname = str(raw.get("nickname") or username)
    pk = str(raw.get("pk") or username)
    mapped_pk = raw.get("mapped_pk")
    settings = {
        "pk": pk,
        "username": username,
        "discord_id": str(raw.get("discord_id") or ""),
        "discord_username": discord_username,
        "avatar_url": raw.get("avatar_url") if isinstance(raw.get("avatar_url"), str) else None,
        "nickname": nickname,
        "profile_visibility": "public" if raw.get("profile_visibility") == "public" else "private",
        "display_name": (str(raw.get("display_name") or "").strip()[:80]) or (discord_username or nickname),
        "bio": str(raw.get("bio") or "").strip()[:280],
        "public_training_summary_enabled": raw.get("public_training_summary_enabled") is True,
        "ranking_country": (
            str(raw.get("ranking_country")).strip()
            if isinstance(raw.get("ranking_country"), str) and raw.get("ranking_country").strip()
            else None
        ),
        "ranking_region": (
            str(raw.get("ranking_region")).strip()
            if isinstance(raw.get("ranking_region"), str) and raw.get("ranking_region").strip()
            else None
        ),
        "age_class": raw.get("age_class") if raw.get("age_class") in AGE_CATEGORY_VALUES else "open",
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }
    if mapped_pk:
        settings["mapped_pk"] = str(mapped_pk)
    return settings


def _mapped_pk_for_settings(settings: dict) -> str:
    return settings.get("mapped_pk") or settings.get("pk") or ""


def _is_self(settings: dict, viewer_username: Optional[str]) -> bool:
    viewer_key = _sanitize_username(viewer_username) if viewer_username else ""
    return bool(viewer_key and viewer_key == (settings.get("username") or ""))


def _can_view(settings: dict, viewer_username: Optional[str]) -> bool:
    return settings.get("profile_visibility") == "public" or _is_self(settings, viewer_username)


def _public_profile(settings: dict, viewer_username: Optional[str]) -> dict:
    return {
        "nickname": settings.get("nickname"),
        "display_name": settings.get("display_name"),
        "avatar_url": settings.get("avatar_url"),
        "bio": settings.get("bio"),
        "profile_visibility": settings.get("profile_visibility"),
        "public_training_summary_enabled": settings.get("public_training_summary_enabled"),
        "is_self": _is_self(settings, viewer_username),
    }


def _positive_number(value) -> Optional[float]:
    return value if isinstance(value, (int, float)) and value > 0 else None


def _resolve_program_sk_sync(health_table, pk: str, version: str = "current") -> str:
    if version == "current":
        pointer = health_table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


def _load_program_sync(health_table, pk: str, sk: str) -> Optional[dict]:
    resp = health_table.get_item(Key={"pk": pk, "sk": sk})
    if not resp.get("Item"):
        return None
    return _sanitize_decimals(resp["Item"])


def _load_sessions_sync(session_table, pk: str, program_sk: str) -> list[dict]:
    prefix = f"session#{program_sk}#"
    items: list[dict] = []
    last_key = None
    while True:
        kwargs = {"KeyConditionExpression": boto3.dynamodb.conditions.Key("pk").eq(pk)
                  & boto3.dynamodb.conditions.Key("sk").begins_with(prefix)}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = session_table.query(**kwargs)
        items.extend(resp.get("Items") or [])
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return [_sanitize_decimals(i) for i in items]


def _has_completed_set(exercise: dict) -> bool:
    set_count = max(0, round(float(exercise.get("sets") or 0)))
    statuses = exercise.get("set_statuses") or []
    if statuses:
        for i in range(set_count):
            if i < len(statuses) and (statuses[i] in (None, "completed")):
                return True
        return False
    failed = exercise.get("failed_set") or []
    if failed:
        legacy = max(set_count, len(failed))
        for i in range(legacy):
            if i < len(failed) and failed[i] is not True:
                return True
        return False
    if exercise.get("failed"):
        return False
    return set_count > 0


def _best_session_lift(program: dict, lift: str) -> Optional[float]:
    best = 0.0
    for session in program.get("sessions") or []:
        if not session.get("completed") or session.get("status") == "skipped":
            continue
        for exercise in session.get("exercises") or []:
            kg = exercise.get("kg")
            if not kg or kg <= best:
                continue
            if not _has_completed_set(exercise):
                continue
            if lift in (exercise.get("name") or "").lower():
                best = kg
    return best if best > 0 else None


def _latest_bodyweight(program: dict) -> Optional[float]:
    candidates = [
        s for s in (program.get("sessions") or [])
        if isinstance(s.get("body_weight_kg"), (int, float)) and s["body_weight_kg"] > 0
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda s: str(s.get("date") or ""), reverse=True)
    return candidates[0]["body_weight_kg"]


def _resolved_lift(program: dict, lift: str) -> Optional[float]:
    meta = program.get("meta") or {}
    current_maxes = program.get("current_maxes") or {}
    manual_maxes = meta.get("manual_maxes") or {}
    target_key = {"squat": "target_squat_kg", "bench": "target_bench_kg", "deadlift": "target_dl_kg"}[lift]
    return (
        _positive_number(current_maxes.get(lift))
        or _positive_number(manual_maxes.get(lift))
        or _best_session_lift(program, lift)
        or _positive_number(meta.get(target_key))
    )


def _calculate_dots(total_kg: float, bodyweight_kg: float, sex: str) -> Optional[float]:
    if total_kg <= 0 or bodyweight_kg <= 0:
        return None
    c = DOTS_COEFFICIENTS.get("female" if sex == "female" else "male")
    denom = c["a"] + c["b"] * bodyweight_kg + c["c"] * bodyweight_kg ** 2 + c["d"] * bodyweight_kg ** 3 + c["e"] * bodyweight_kg ** 4
    if abs(denom) < 1e-12:
        return None
    return round((500 / denom) * total_kg, 2)


def _video_library_items(sessions: list[dict]) -> list[dict]:
    items = []
    for session in sessions:
        for video in session.get("videos") or []:
            items.append({
                "video": video,
                "session_date": session.get("date"),
                "day": session.get("day"),
                "week_number": session.get("week_number"),
                "phase_name": (session.get("phase") or {}).get("name", ""),
            })
    items.sort(
        key=lambda it: (str(it.get("session_date") or ""), str((it.get("video") or {}).get("uploaded_at") or "")),
        reverse=True,
    )
    return items


def _build_profile(settings: dict, viewer_username: Optional[str], program: Optional[dict], sessions: list[dict]) -> dict:
    base = _public_profile(settings, viewer_username)
    if not program:
        return {
            **base,
            "federation": None,
            "weight_class_kg": None,
            "practicing_for": None,
            "summary": {"squat_kg": None, "bench_kg": None, "deadlift_kg": None, "total_kg": None, "bodyweight_kg": None, "dots": None},
            "lift_videos": [],
        }
    meta = program.get("meta") or {}
    squat = _resolved_lift(program, "squat")
    bench = _resolved_lift(program, "bench")
    deadlift = _resolved_lift(program, "deadlift")
    total = (squat + bench + deadlift) if (squat is not None and bench is not None and deadlift is not None) else None
    bodyweight = (
        _positive_number(meta.get("current_body_weight_kg"))
        or _latest_bodyweight(program)
        or _positive_number((meta.get("last_comp") or {}).get("body_weight_kg"))
    )
    sex = "female" if meta.get("sex") == "female" else "male"
    dots = _calculate_dots(total, bodyweight, sex) if total is not None and bodyweight is not None else None
    video_items = _video_library_items(sessions)
    return {
        **base,
        "federation": meta.get("federation") or None,
        "weight_class_kg": _positive_number(meta.get("weight_class_kg")),
        "practicing_for": meta.get("practicing_for") or None,
        "summary": {"squat_kg": squat, "bench_kg": bench, "deadlift_kg": deadlift, "total_kg": total, "bodyweight_kg": bodyweight, "dots": dots},
        "lift_videos": video_items[:24],
    }


def _get_settings_by_mapped_pk_sync(user_table, mapped_pk: str, viewer_username: Optional[str]) -> Optional[dict]:
    target = (mapped_pk or "").strip()
    if not target or not MAPPED_PK_RE.match(target):
        return None
    direct = user_table.get_item(Key={"pk": target})
    if direct.get("Item"):
        settings = _normalize_settings(_sanitize_decimals(direct["Item"]))
        return settings if _can_view(settings, viewer_username) else None
    last_key = None
    while True:
        kwargs = {"FilterExpression": boto3.dynamodb.conditions.Attr("mapped_pk").eq(target), "Limit": 1}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = user_table.scan(**kwargs)
        for item in resp.get("Items") or []:
            settings = _normalize_settings(_sanitize_decimals(item))
            if _can_view(settings, viewer_username):
                return settings
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return None


async def profile_get_current(args: dict) -> dict:
    """Build the current user's profile (looked up by mapped_pk).

    Args:
        args: dict with optional `mapped_pk` (defaults to 'operator'),
              and `viewer_username` (requesting user for visibility checks).
    """
    user_table = _get_user_table()
    health_table = _get_health_table()
    session_table = _get_session_table()
    mapped_pk = args.get("mapped_pk") or "operator"
    viewer_username = args.get("viewer_username")

    def _sync():
        settings = _get_settings_by_mapped_pk_sync(user_table, mapped_pk, viewer_username)
        if not settings:
            return None
        pk = _mapped_pk_for_settings(settings)
        program_sk = _resolve_program_sk_sync(health_table, pk, "current")
        program = _load_program_sync(health_table, pk, program_sk)
        sessions = _load_sessions_sync(session_table, pk, program_sk) if program else []
        return _build_profile(settings, viewer_username, program, sessions)

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    if result is None:
        raise ValueError("Profile not found")
    return result