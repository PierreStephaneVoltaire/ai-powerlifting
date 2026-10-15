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
MAX_FEDERATIONS = 20
MAX_DISPLAY_NAME = 80
MAX_BIO = 280


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SettingsUpdateOnboardingProfile] User table initialised: %s", table_name)
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


def _validate(input_data: dict) -> dict:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    display_name = input_data.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("display_name is required")
    display_name_v = display_name.strip()[:MAX_DISPLAY_NAME]
    if not display_name_v:
        raise ValueError("display_name cannot be empty")
    bio = input_data.get("bio")
    if bio is not None and not isinstance(bio, str):
        raise ValueError("bio must be a string")
    bio_v = str(bio).strip()[:MAX_BIO] if isinstance(bio, str) else ""
    visibility = input_data.get("profile_visibility")
    if visibility is not None and visibility not in ("private", "public"):
        raise ValueError("profile_visibility must be 'private' or 'public'")
    visibility_v = visibility or "private"
    summary = input_data.get("public_training_summary_enabled")
    summary_v = bool(summary) if summary is not None else False
    federations_raw = input_data.get("federations")
    federations: list[str] = []
    if federations_raw is None:
        federations = None  # type: ignore[assignment]
    elif isinstance(federations_raw, list):
        for item in federations_raw:
            if isinstance(item, str):
                v = item.strip()
                if v and v not in federations:
                    federations.append(v)
            if len(federations) >= MAX_FEDERATIONS:
                break
    else:
        raise ValueError("federations must be an array of strings")
    return {
        "display_name": display_name_v,
        "bio": bio_v,
        "profile_visibility": visibility_v,
        "public_training_summary_enabled": summary_v,
        "federations": federations,
    }


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
    roles_raw = raw.get("roles")
    roles: list[str] = []
    if isinstance(roles_raw, list):
        for item in roles_raw:
            if isinstance(item, str) and item in ROLE_VALUES and item not in roles:
                roles.append(item)
    active_role = raw.get("active_role") if raw.get("active_role") in ROLE_VALUES else (roles[0] if roles else "athlete")
    sex = raw.get("sex")
    country = raw.get("country")
    region = raw.get("region")
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
    if country and isinstance(country, str):
        settings["country"] = country.strip()[:8].upper()
    if region and isinstance(region, str):
        settings["region"] = region.strip()[:64]
    if mapped_pk:
        settings["mapped_pk"] = str(mapped_pk)
    return settings


async def settings_update_onboarding_profile(args: dict) -> dict:
    """Update profile and federations during onboarding.

    Required: display_name.
    Optional: bio, profile_visibility, public_training_summary_enabled,
    federations (array of federation IDs).

    Marks `profile_complete = True`.
    """
    table = _get_table()
    username = args.get("username") or ""
    if not username:
        raise ValueError("username is required")
    input_data = args.get("input") or args
    validated = _validate(input_data)

    def _sync():
        existing = _get_existing_sync(table, username)
        if not existing:
            raise ValueError("Settings not found")
        now = datetime.now(timezone.utc).isoformat()
        update_expr = (
            "SET display_name = :display, bio = :bio, profile_visibility = :visibility, "
            "public_training_summary_enabled = :summary, profile_complete = :complete, "
            "updated_at = :now"
        )
        values = {
            ":display": validated["display_name"],
            ":bio": validated["bio"],
            ":visibility": validated["profile_visibility"],
            ":summary": validated["public_training_summary_enabled"],
            ":complete": True,
            ":now": now,
        }
        if validated["federations"] is not None:
            update_expr += ", federations = :federations"
            values[":federations"] = validated["federations"]
        table.update_item(
            Key={"pk": existing["pk"]},
            UpdateExpression=update_expr,
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues=values,
        )
        updated = _get_existing_sync(table, username)
        return _normalize_settings(updated or existing)

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
