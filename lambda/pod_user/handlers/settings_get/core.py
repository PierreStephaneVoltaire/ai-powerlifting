from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger(__name__)

_table = None

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
MAX_TAG_LENGTH = 30
TAG_RE = re.compile(r"^[a-z0-9_-]{1,30}$")


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SettingsTools] User table initialised: %s", table_name)
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


def _normalize_tag(raw) -> Optional[str]:
    tag = str(raw or "").strip().lower().replace(" ", "-")[:MAX_TAG_LENGTH]
    return tag if TAG_RE.match(tag) else None


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
        if not tag or tag in seen:
            continue
        seen.add(tag)
        result.append({"tag": tag, "approved": approved, "proposed_by": proposed_by})
    return result[:MAX_TAGS]


def _default_operator_settings() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "pk": "operator",
        "username": "operator",
        "discord_id": "",
        "discord_username": "operator",
        "avatar_url": None,
        "nickname": "operator",
        "profile_visibility": "private",
        "display_name": "operator",
        "bio": "",
        "public_training_summary_enabled": False,
        "ranking_country": None,
        "ranking_region": None,
        "age_class": "open",
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }


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
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(raw.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }
    if mapped_pk:
        settings["mapped_pk"] = str(mapped_pk)
    return settings


def _get_settings_by_username_sync(table, discord_username: str) -> Optional[dict]:
    key = _sanitize_username(discord_username)
    resp = table.get_item(Key={"pk": key})
    item = resp.get("Item")
    if not item:
        return None
    return _normalize_settings(_sanitize_decimals(item))


def _get_settings_by_mapped_pk_sync(table, mapped_pk: str) -> Optional[dict]:
    target = (mapped_pk or "").strip()
    if not target or not MAPPED_PK_RE.match(target):
        return None
    direct = table.get_item(Key={"pk": target})
    if direct.get("Item"):
        return _normalize_settings(_sanitize_decimals(direct["Item"]))
    resp = table.scan(FilterExpression=Attr("mapped_pk").eq(target), Limit=1)
    items = resp.get("Items") or []
    if not items:
        return None
    return _normalize_settings(_sanitize_decimals(items[0]))


async def settings_get(args: dict) -> dict:
    """Get user settings by discord username or mapped pk.

    Args:
        args: dict with optional `username` (discord username) and `mapped_pk`.
              If neither resolves a record and no `username` is supplied, a
              default operator settings object is returned.
    """
    table = _get_table()
    username = args.get("username")
    mapped_pk = args.get("mapped_pk")

    def _sync():
        if username:
            settings = _get_settings_by_username_sync(table, username)
            if settings:
                return settings
        if mapped_pk:
            settings = _get_settings_by_mapped_pk_sync(table, mapped_pk)
            if settings:
                return settings
        if not username:
            return _default_operator_settings()
        return None

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    if result is None:
        raise ValueError("Settings not found")
    return result