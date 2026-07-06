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


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_USER_TABLE", "if-user")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[ProfileTools] User table initialised: %s", table_name)
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


def _scan_settings_sync(table) -> list[dict]:
    settings_list: list[dict] = []
    last_key = None
    while True:
        kwargs = {}
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.scan(**kwargs)
        for item in resp.get("Items") or []:
            settings_list.append(_normalize_settings(_sanitize_decimals(item)))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
    return settings_list


async def profile_search(args: dict) -> dict:
    """Search public profiles by substring across nickname/display_name/bio.

    Args:
        args: dict with optional `query` (substring) and `viewer_username`
              (the requesting user, used to include private self profiles).
    """
    table = _get_table()
    query = (args.get("query") or "").strip().lower()
    viewer_username = args.get("viewer_username")

    def _sync():
        all_settings = _scan_settings_sync(table)
        results = []
        for settings in all_settings:
            if not _can_view(settings, viewer_username):
                continue
            if not query:
                results.append(settings)
                continue
            haystack = [
                settings.get("nickname") or "",
                settings.get("display_name") or "",
                settings.get("discord_username") or "",
                settings.get("bio") or "",
            ]
            if any(query in str(v).lower() for v in haystack):
                results.append(settings)
        results.sort(key=lambda s: str(s.get("display_name") or "").lower())
        return [_public_profile(s, viewer_username) for s in results[:50]]

    profiles = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return {"profiles": profiles}