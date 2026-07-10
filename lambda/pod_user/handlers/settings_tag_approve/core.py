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


def _get_existing_sync(table, discord_username: str) -> Optional[dict]:
    key = _sanitize_username(discord_username)
    resp = table.get_item(Key={"pk": key})
    item = resp.get("Item")
    if not item:
        return None
    return _normalize_settings(_sanitize_decimals(item))


async def settings_tag_approve(args: dict) -> dict:
    """Approve a proposed tag on the athlete's own profile.

    Args:
        args: dict with required `username` (discord username) and `tag` (string).
    """
    table = _get_table()
    username = args.get("username") or ""
    tag = _normalize_tag(args.get("tag"))
    if not tag:
        raise ValueError("Invalid tag")

    def _sync():
        existing = _get_existing_sync(table, username)
        if not existing:
            raise ValueError("Settings not found")
        tags = existing.get("tags") or []
        found = False
        for t in tags:
            if t.get("tag") == tag:
                t["approved"] = True
                found = True
                break
        if not found:
            raise ValueError("Tag not found")
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"pk": existing["pk"]},
            UpdateExpression="SET tags = :tags, updated_at = :now",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":tags": tags, ":now": now},
        )
        updated = _get_existing_sync(table, username)
        return updated or existing

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
