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
MIN_BODYWEIGHT_KG = 30.0
MAX_BODYWEIGHT_KG = 300.0
MIN_LIFT_KG = 20.0
MAX_LIFT_KG = 600.0


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SettingsUpdateAthleteBasics] User table initialised: %s", table_name)
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


def _to_positive_float(value, *, lo: float, hi: float, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a finite number")
    if v < lo or v > hi:
        raise ValueError(f"{name} must be between {lo} and {hi} kg")
    return round(v, 2)


def _validate_athlete_basics(input_data: dict) -> dict:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    sex = input_data.get("sex")
    if sex not in SEX_VALUES:
        raise ValueError("sex must be 'male' or 'female'")
    country = input_data.get("country")
    if not isinstance(country, str) or not country.strip():
        raise ValueError("country is required")
    country_v = country.strip().upper()
    if len(country_v) > 8:
        raise ValueError("country must be a short code (<= 8 chars)")
    region = input_data.get("region")
    if region is not None and not isinstance(region, str):
        raise ValueError("region must be a string")
    region_v = str(region).strip()[:64] if isinstance(region, str) and str(region).strip() else None
    bodyweight = _to_positive_float(
        input_data.get("bodyweight_kg"),
        lo=MIN_BODYWEIGHT_KG,
        hi=MAX_BODYWEIGHT_KG,
        name="bodyweight_kg",
    )
    maxes = input_data.get("training_maxes")
    if not isinstance(maxes, dict):
        raise ValueError("training_maxes is required")
    squat = _to_positive_float(maxes.get("squat_kg"), lo=MIN_LIFT_KG, hi=MAX_LIFT_KG, name="squat_kg")
    bench = _to_positive_float(maxes.get("bench_kg"), lo=MIN_LIFT_KG, hi=MAX_LIFT_KG, name="bench_kg")
    deadlift = _to_positive_float(maxes.get("deadlift_kg"), lo=MIN_LIFT_KG, hi=MAX_LIFT_KG, name="deadlift_kg")
    return {
        "sex": sex,
        "country": country_v,
        "region": region_v,
        "bodyweight_kg": bodyweight,
        "training_maxes": {
            "squat_kg": squat,
            "bench_kg": bench,
            "deadlift_kg": deadlift,
        },
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
    sex = raw.get("sex")
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


async def settings_update_athlete_basics(args: dict) -> dict:
    """Update athlete basics.

    Required: sex, country, region (or null), bodyweight_kg, training_maxes
    (squat_kg/bench_kg/deadlift_kg).

    Marks `athlete_basics_complete = True`. No-op for users who don't have the
    'athlete' role.
    """
    table = _get_table()
    username = args.get("username") or ""
    if not username:
        raise ValueError("username is required")
    input_data = args.get("input") or args
    validated = _validate_athlete_basics(input_data)

    def _sync():
        existing = _get_existing_sync(table, username)
        if not existing:
            raise ValueError("Settings not found")
        roles = existing.get("roles") or []
        if isinstance(roles, list) and "athlete" not in roles:
            raise ValueError("User does not have the 'athlete' role")
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"pk": existing["pk"]},
            UpdateExpression=(
                "SET sex = :sex, country = :country, region = :region, "
                "bodyweight_kg = :bodyweight, training_maxes = :maxes, "
                "athlete_basics_complete = :complete, updated_at = :now"
            ),
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={
                ":sex": validated["sex"],
                ":country": validated["country"],
                ":region": validated["region"],
                ":bodyweight": Decimal(str(validated["bodyweight_kg"])),
                ":maxes": {
                    "squat_kg": Decimal(str(validated["training_maxes"]["squat_kg"])),
                    "bench_kg": Decimal(str(validated["training_maxes"]["bench_kg"])),
                    "deadlift_kg": Decimal(str(validated["training_maxes"]["deadlift_kg"])),
                },
                ":complete": True,
                ":now": now,
            },
        )
        updated = _get_existing_sync(table, username)
        return _normalize_settings(updated or existing)

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
