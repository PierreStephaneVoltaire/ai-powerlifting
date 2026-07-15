from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

_table = None
_s3 = None

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
MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SettingsTools] User table initialised: %s", table_name)
    return _table


def _get_s3():
    global _s3
    if _s3 is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        _s3 = boto3.client("s3", region_name=region)
        logger.info("[SettingsTools] S3 client initialised")
    return _s3


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
        "sex": raw.get("sex") if raw.get("sex") in SEX_VALUES else None,
        "bodyweight_kg": _to_float(raw.get("bodyweight_kg")),
        "training_maxes": _normalize_training_maxes(raw.get("training_maxes")),
        "federations": _normalize_federations(raw.get("federations")),
        "roles": _normalize_roles(raw.get("roles")),
        "active_role": _normalize_role(raw.get("active_role")) or ((_normalize_roles(raw.get("roles")) or ["athlete"])[0]),
        "athlete_basics_complete": bool(raw.get("athlete_basics_complete")),
        "profile_complete": bool(raw.get("profile_complete")),

        "age_class": raw.get("age_class") if raw.get("age_class") in AGE_CATEGORY_VALUES else "open",
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }
    if mapped_pk:
        settings["mapped_pk"] = str(mapped_pk)
    return settings


def _get_existing_sync(table, discord_username: str) -> Optional[dict]:
    key = _sanitize_username(discord_username)
    resp = table.get_item(Key={"pk": key})
    item = resp.get("Item")
    if not item:
        return None
    return _normalize_settings(_sanitize_decimals(item))


def _s3_safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value or "")[:128] or "user"


def _avatar_extension(mimetype: str, filename: str) -> str:
    ext = MIME_EXT.get(mimetype)
    if ext:
        return ext
    parts = (filename or "").split(".")
    return (parts[-1].lower() if len(parts) > 1 else "jpg") or "jpg"


def _profile_avatar_key_from_url(value) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str) and value.startswith("http://") or (isinstance(value, str) and value.startswith("https://")):
        try:
            from urllib.parse import urlparse, unquote

from .._shared.settings_normalize import (
    SEX_VALUES,
    ROLE_VALUES,
    _to_float,
    _normalize_role,
    _normalize_roles,
    _normalize_training_maxes,
    _normalize_federations,
)
            return unquote(urlparse(value).path).lstrip("/")
        except Exception:
            return None
    if isinstance(value, str) and value.startswith("profiles/"):
        return value
    return None


async def settings_update_avatar(args: dict) -> dict:
    """Upload a profile avatar to S3 and set avatar_url on the user settings.

    Args:
        args: dict with required `username`, `file_b64` (base64-encoded bytes),
              `mimetype`, and optional `filename`, `mapped_pk`.
    """
    table = _get_table()
    s3 = _get_s3()
    bucket = os.environ.get("VIDEOS_BUCKET", "powerlifting-session-videos")
    username = args.get("username") or ""
    file_b64 = args.get("file_b64") or ""
    mimetype = args.get("mimetype") or "image/jpeg"
    filename = args.get("filename") or "avatar.jpg"

    def _sync():
        existing = _get_existing_sync(table, username)
        if not existing:
            raise ValueError("Settings not found")
        body = base64.b64decode(file_b64) if file_b64 else b""
        if not body:
            raise ValueError("No profile picture provided")
        avatar_id = str(uuid.uuid4())
        extension = _avatar_extension(mimetype, filename)
        owner = _s3_safe_segment(args.get("mapped_pk") or existing["pk"])
        s3_key = f"profiles/{owner}/avatars/{avatar_id}.{extension}"
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=body,
            ContentType=mimetype,
            Metadata={
                "profile_avatar": "true",
                "username": existing.get("username", ""),
                "mapped_pk": owner,
            },
        )
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"pk": existing["pk"]},
            UpdateExpression="SET avatar_url = :avatar, updated_at = :now",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":avatar": s3_key, ":now": now},
        )
        previous_key = _profile_avatar_key_from_url(existing.get("avatar_url"))
        if previous_key and previous_key != s3_key:
            try:
                s3.delete_object(Bucket=bucket, Key=previous_key)
            except Exception as exc:
                logger.warning("[SettingsTools] Failed to delete previous avatar: %s", exc)
        updated = _get_existing_sync(table, username)
        return updated or existing

    return await asyncio.get_running_loop().run_in_executor(None, _sync)