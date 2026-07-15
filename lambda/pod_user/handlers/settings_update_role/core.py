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

_table = None

NICKNAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")
AGE_CATEGORY_VALUES = (
    "open",
    "subjunior",
    "junior",
    "master1",
    "master2",
    "master3",
    "master4",
)
SEX_VALUES = ("male", "female")
ROLE_VALUES = ("athlete", "coach", "handler")


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SettingsUpdateRole] User table initialised: %s", table_name)
    return _table


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


def _read_roles(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for item in raw:
        if isinstance(item, str) and item in ROLE_VALUES and item not in seen:
            seen.append(item)
    return seen


def _get_existing_sync(table, discord_username: str) -> Optional[dict]:
    key = _sanitize_username(discord_username)
    resp = table.get_item(Key={"pk": key})
    item = resp.get("Item")
    if not item:
        return None
    return _sanitize_decimals(item)


def _normalize_settings(raw: dict) -> dict:
    discord_username = str(raw.get("discord_username") or raw.get("username") or "")
    username = _sanitize_username(str(raw.get("username") or discord_username or raw.get("nickname") or "user"))
    nickname = str(raw.get("nickname") or username)
    pk = str(raw.get("pk") or username)
    mapped_pk = raw.get("mapped_pk")
    bw = raw.get("bodyweight_kg")
    bw_float = float(bw) if isinstance(bw, (int, float, Decimal)) and float(bw) > 0 else None
    maxes = raw.get("training_maxes")
    if isinstance(maxes, dict):
        try:
            training_maxes = {
                "squat_kg": float(maxes.get("squat_kg")),
                "bench_kg": float(maxes.get("bench_kg")),
                "deadlift_kg": float(maxes.get("deadlift_kg")),
            }
        except (TypeError, ValueError):
            training_maxes = None
    else:
        training_maxes = None
    federations_raw = raw.get("federations")
    federations: list[str] = []
    if isinstance(federations_raw, list):
        for item in federations_raw:
            if isinstance(item, str):
                v = item.strip()
                if v and v not in federations:
                    federations.append(v)
    roles = _read_roles(raw.get("roles"))
    active_role = raw.get("active_role") if raw.get("active_role") in ROLE_VALUES else (roles[0] if roles else "athlete")
    sex = raw.get("sex")
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
        "ranking_country": raw.get("ranking_country") if isinstance(raw.get("ranking_country"), str) else None,
        "ranking_region": raw.get("ranking_region") if isinstance(raw.get("ranking_region"), str) else None,
        "age_class": raw.get("age_class") if raw.get("age_class") in AGE_CATEGORY_VALUES else "open",
        "sex": sex if sex in SEX_VALUES else None,
        "bodyweight_kg": bw_float,
        "training_maxes": training_maxes,
        "federations": federations,
        "roles": roles,
        "active_role": active_role,
        "athlete_basics_complete": bool(raw.get("athlete_basics_complete")),
        "profile_complete": bool(raw.get("profile_complete")),
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }
    if mapped_pk:
        settings["mapped_pk"] = str(mapped_pk)
    return settings


async def settings_update_role(args: dict) -> dict:
    """Set the user's roles and active role.

    Args:
        args: dict with required `username`, `roles` (array of 'athlete' |
              'coach' | 'handler', at least one), and optional
              `active_role` (must be one of `roles`).

    The first role in the list is used as the default active_role when none
    is provided. This lambda is what the user-facing "Switch role" UI calls
    on the backend; the JWT `roles`/`active_role` claims are then re-issued
    by the auth flow on the next token refresh.
    """
    table = _get_table()
    username = args.get("username") or ""
    if not username:
        raise ValueError("username is required")
    new_roles = _read_roles(args.get("roles"))
    if not new_roles:
        raise ValueError("At least one role is required")
    active_role = args.get("active_role")
    if active_role is not None and active_role not in new_roles:
        raise ValueError("active_role must be one of the assigned roles")
    if active_role is None:
        active_role = new_roles[0]

    def _sync():
        existing = _get_existing_sync(table, username)
        if not existing:
            raise ValueError("Settings not found")
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"pk": existing["pk"]},
            UpdateExpression="SET roles = :roles, active_role = :active, updated_at = :now",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={
                ":roles": new_roles,
                ":active": active_role,
                ":now": now,
            },
        )
        updated = _get_existing_sync(table, username)
        return _normalize_settings(updated or existing)

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
