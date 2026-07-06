from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)

_table = None

NICKNAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SettingsCreate] User table initialised: %s", table_name)
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


def _to_dynamo(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _normalize_settings(raw: dict) -> dict:
    discord_username = str(raw.get("discord_username") or raw.get("username") or "")
    username = str(raw.get("username") or "")
    nickname = str(raw.get("nickname") or username)
    pk = str(raw.get("pk") or username)
    avatar = raw.get("avatar_url")
    return {
        "pk": pk,
        "username": username,
        "discord_id": str(raw.get("discord_id") or ""),
        "discord_username": discord_username,
        "avatar_url": avatar if isinstance(avatar, str) else None,
        "nickname": nickname,
        "profile_visibility": "public" if raw.get("profile_visibility") == "public" else "private",
        "display_name": (str(raw.get("display_name") or "").strip()[:80]) or (discord_username or nickname),
        "bio": str(raw.get("bio") or "").strip()[:280],
        "public_training_summary_enabled": raw.get("public_training_summary_enabled") is True,
        "ranking_country": raw.get("ranking_country") if isinstance(raw.get("ranking_country"), str) else None,
        "ranking_region": raw.get("ranking_region") if isinstance(raw.get("ranking_region"), str) else None,
        "age_class": raw.get("age_class") if raw.get("age_class") in ("open", "subjunior", "junior", "master1", "master2", "master3", "master4") else "open",
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }


def _get_by_pk_sync(table, pk: str) -> Optional[dict]:
    resp = table.get_item(Key={"pk": pk})
    item = resp.get("Item")
    if not item:
        return None
    return _normalize_settings(_sanitize_decimals(item))


def _create_sync(discord_id: str, discord_username: str, avatar_url: Optional[str]):
    """Conditionally create the initial user row; on race, return the winner."""
    from botocore.exceptions import ClientError
    table = _get_table()
    username = _sanitize_username(discord_username)
    now = datetime.now(timezone.utc).isoformat()
    default = {
        "pk": username,
        "username": username,
        "discord_id": str(discord_id or ""),
        "discord_username": str(discord_username or ""),
        "avatar_url": avatar_url if isinstance(avatar_url, str) else None,
        "nickname": username,
        "profile_visibility": "private",
        "display_name": str(discord_username or ""),
        "bio": "",
        "public_training_summary_enabled": False,
        "ranking_country": None,
        "ranking_region": None,
        "age_class": "open",
        "created_at": now,
        "updated_at": now,
    }
    created = True
    try:
        table.put_item(Item=_to_dynamo(default), ConditionExpression="attribute_not_exists(pk)")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            created = False
        else:
            raise
    if not created:
        raced = _get_by_pk_sync(table, username)
        if raced:
            return {"settings": raced, "created": False}
    return {"settings": _normalize_settings(default), "created": created}


async def settings_create(args: dict) -> dict:
    """Create the initial user settings row on first Discord login.

    Conditional put (attribute_not_exists(pk)) so concurrent first-logins don't
    overwrite each other; on a race the existing row is returned. Returns
    {settings, created}.

    Args:
        args: dict with `discord_id`, `discord_username`, optional `avatar_url`.
    """
    discord_id = args.get("discord_id") or ""
    discord_username = args.get("discord_username") or ""
    avatar_url = args.get("avatar_url")
    return await asyncio.get_running_loop().run_in_executor(
        None, lambda: _create_sync(discord_id, discord_username, avatar_url)
    )
