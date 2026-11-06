from __future__ import annotations

import asyncio
from importlib import import_module
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional


from .._shared.settings_normalize import (
    SEX_VALUES,
    _to_float,
    _normalize_role,
    _normalize_roles,
    _normalize_training_maxes,
    _normalize_federations,
)

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
MAX_TAGS = 20


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


def _normalize_tag(raw) -> Optional[str]:
    from services.tag_catalog import normalize_tag
    try:
        return normalize_tag(str(raw or ""))
    except ValueError:
        return None


def _normalize_tags(raw_tags) -> list[dict]:
    if not isinstance(raw_tags, list):
        return []
    seen = set()
    result = []
    for item in raw_tags:
        if isinstance(item, dict):
            tag = _normalize_tag(item.get("tag"))
            approved = bool(item.get("approved"))
            proposed_by = str(item.get("proposed_by") or "")
        elif isinstance(item, str):
            tag = _normalize_tag(item)
            approved = True
            proposed_by = ""
        else:
            continue
        if not tag or tag.casefold() in seen:
            continue
        seen.add(tag.casefold())
        result.append({"tag": tag, "approved": approved, "proposed_by": proposed_by})
    return result[:MAX_TAGS]


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
        "tags": _normalize_tags(raw.get("tags")),
        "sex": raw.get("sex") if raw.get("sex") in SEX_VALUES else None,
        "bodyweight_kg": _to_float(raw.get("bodyweight_kg")),
        "training_maxes": _normalize_training_maxes(raw.get("training_maxes")),
        "federations": _normalize_federations(raw.get("federations")),
        "roles": _normalize_roles(raw.get("roles")),
        "active_role": _normalize_role(raw.get("active_role")) or ((_normalize_roles(raw.get("roles")) or ["athlete"])[0]),
        "athlete_basics_complete": bool(raw.get("athlete_basics_complete")),
        "profile_complete": bool(raw.get("profile_complete")),
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }
    if mapped_pk:
        settings["mapped_pk"] = str(mapped_pk)
    return settings


def _is_self(settings: dict, viewer_username: Optional[str]) -> bool:
    viewer_key = _sanitize_username(viewer_username) if viewer_username else ""
    return bool(viewer_key and viewer_key == (settings.get("username") or ""))


def _public_profile(settings: dict, viewer_username: Optional[str]) -> dict:
    return {
        "nickname": settings.get("nickname"),
        "display_name": settings.get("display_name"),
        "avatar_url": settings.get("avatar_url"),
        "bio": settings.get("bio"),
        "profile_visibility": settings.get("profile_visibility"),
        "public_training_summary_enabled": settings.get("public_training_summary_enabled"),
        "is_self": _is_self(settings, viewer_username),
        "tags": [t["tag"] for t in (settings.get("tags") or []) if t.get("approved")],
    }


def _positive_number(value) -> Optional[float]:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


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


def _has_completed_set(exercise: dict) -> bool:
    set_count = max(0, round(float(exercise.get("sets") or 0)))
    statuses = exercise.get("set_statuses") or []
    if statuses:
        for i in range(set_count):
            if i < len(statuses) and (statuses[i] in (None, "completed")):
                return True
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
    return (
        _positive_number(current_maxes.get(lift))
        or _positive_number(manual_maxes.get(lift))
        or _best_session_lift(program, lift)
    )


def _calculate_dots(total_kg: float, bodyweight_kg: float, sex: str) -> Optional[float]:
    if total_kg <= 0 or bodyweight_kg <= 0:
        return None
    calculate_dots = import_module("services.handlers.calculations.calculate_dots.core").calculate_dots
    return calculate_dots(total_kg, bodyweight_kg, sex)


def _video_library_items(sessions: list[dict]) -> list[dict]:
    items = []
    for session in sessions:
        for video in session.get("videos") or []:
            items.append({
                "video": video,
                "session_id": session.get('id') or session.get('session_id'),
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
    program = {**program, "sessions": sessions}
    meta = program.get("meta") or {}
    squat = _resolved_lift(program, "squat")
    bench = _resolved_lift(program, "bench")
    deadlift = _resolved_lift(program, "deadlift")
    total = (squat + bench + deadlift) if (squat is not None and bench is not None and deadlift is not None) else None
    bodyweight = (
        _positive_number(meta.get("current_body_weight_kg"))
        or _latest_bodyweight(program)
    )
    sex = meta.get("sex") or settings.get("sex")
    dots = _calculate_dots(total, bodyweight, sex) if total is not None and bodyweight is not None and sex in ("male", "female") else None
    video_items = _video_library_items(sessions)
    return {
        **base,
        "federation": meta.get("federation") or None,
        "weight_class_kg": _positive_number(meta.get("weight_class_kg")),
        "practicing_for": meta.get("practicing_for") or None,
        "summary": {"squat_kg": squat, "bench_kg": bench, "deadlift_kg": deadlift, "total_kg": total, "bodyweight_kg": bodyweight, "dots": dots},
        "lift_videos": video_items,
    }


async def profile_get(args: dict) -> dict:
    from services.profile_views import get_by_handle
    return await asyncio.to_thread(get_by_handle, args)
