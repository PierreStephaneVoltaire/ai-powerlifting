"""DynamoDB-backed store for the powerlifting user settings table.

Mirrors the TypeScript ``backend/src/services/userSettings.ts`` so the
fission functions are thin async wrappers. The user table schema is:

  pk = <username>                -> UserSettings (the row itself is the user)
  global_username_index GSI      -> allows looking up by discord_username

The store supports lookup by username OR by mapped_pk (the portal's
operator-scoped identifier). It validates nickname + mapped_pk and
sanitises inputs the same way the backend does.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger(__name__)

NICKNAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")
MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")

AGE_CATEGORY_VALUES = (
    "open", "subjunior", "junior",
    "master1", "master2", "master3", "master4",
)

VISIBILITY_VALUES = ("private", "public")


def _sanitize_username(username: Any) -> str:
    if not isinstance(username, str) or not username:
        return f"user_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    sanitized = re.sub(r"[^a-z0-9_-]", "_", username.lower())[:32]
    if NICKNAME_RE.match(sanitized):
        return sanitized
    return f"user_{int(datetime.now(timezone.utc).timestamp() * 1000)}"


def _to_dynamo(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _sanitize_decimals(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_nickname(value: Any) -> bool:
    return bool(NICKNAME_RE.match(value or ""))


def _validate_mapped_pk(value: Any) -> bool:
    return bool(MAPPED_PK_RE.match(value or ""))


def _normalize_visibility(value: Any) -> str:
    return value if value in VISIBILITY_VALUES else "private"


def _normalize_age_class(value: Any) -> str:
    return value if value in AGE_CATEGORY_VALUES else "open"


def _normalize_display_name(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    s = value.strip()[:80]
    return s or fallback


def _normalize_bio(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:280]


def _normalize_mapped_pk(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    s = value.strip()
    return s if _validate_mapped_pk(s) else None


class UserSettingsStore:
    """Async store for the ``if-user`` table (powerlifting portal user settings)."""

    def __init__(
        self,
        table_name: Optional[str] = None,
        region: str = "ca-central-1",
    ) -> None:
        self._table_name = table_name or os.environ.get("IF_USER_TABLE", "if-user")
        self._region = region or os.environ.get("AWS_REGION", "ca-central-1")
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(
                self._table_name
            )
        return self._table

    def _get_sync(self, pk: str) -> Optional[dict]:
        resp = self.table.get_item(Key={"pk": pk})
        item = resp.get("Item")
        return _sanitize_decimals(item) if item else None

    async def get_by_username(self, username: str) -> Optional[dict]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._get_sync(_sanitize_username(username))
        )

    def _scan_mapped_pk_sync(self, mapped_pk: str) -> Optional[dict]:
        try:
            resp = self.table.scan(
                FilterExpression=Attr("mapped_pk").eq(mapped_pk),
                Limit=50,
            )
        except Exception as exc:
            logger.warning("[UserSettingsStore] scan_mapped_pk failed: %s", exc)
            resp = {"Items": []}
        items = resp.get("Items") or []
        if items:
            items.sort(key=lambda it: str(it.get("updated_at") or ""), reverse=True)
            return _sanitize_decimals(items[0])
        return self._get_sync(mapped_pk)

    async def get_by_mapped_pk(self, mapped_pk: str) -> Optional[dict]:
        if not _validate_mapped_pk(mapped_pk):
            return None
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._scan_mapped_pk_sync(mapped_pk)
        )

    def _get_or_create_default_sync(self, pk: str) -> dict:
        existing = self._get_sync(pk)
        if existing:
            return existing
        now = _now_iso()
        return {
            "pk": pk,
            "username": pk,
            "discord_id": "",
            "discord_username": pk,
            "avatar_url": None,
            "nickname": pk,
            "profile_visibility": "private",
            "display_name": pk,
            "bio": "",
            "public_training_summary_enabled": False,
            "ranking_country": None,
            "ranking_region": None,
            "age_class": "open",
            "created_at": now,
            "updated_at": now,
        }

    async def get_or_create_default(self, username: str) -> dict:
        pk = _sanitize_username(username)
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._get_or_create_default_sync(pk)
        )


    def _update_nickname_sync(self, username: str, nickname: str) -> dict:
        if not _validate_nickname(nickname):
            raise ValueError("nickname must match ^[a-z0-9_-]{2,32}$")
        pk = _sanitize_username(username)
        existing = self._get_or_create_default_sync(pk)
        new_pk = _sanitize_username(nickname)
        if new_pk != pk:
            now = _now_iso()
            new_item = dict(existing)
            new_item["pk"] = new_pk
            new_item["nickname"] = nickname
            new_item["username"] = new_pk
            new_item["updated_at"] = now
            try:
                self.table.put_item(
                    Item=_to_dynamo(new_item),
                    ConditionExpression="attribute_not_exists(pk)",
                )
            except Exception as exc:
                raise ValueError(f"nickname already in use: {new_pk}") from exc
            self.table.delete_item(Key={"pk": pk})
            return new_item
        existing["nickname"] = nickname
        existing["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(existing))
        return existing

    async def update_nickname(self, username: str, nickname: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._update_nickname_sync(username, nickname)
        )

    def _update_profile_sync(
        self,
        username: str,
        visibility: Optional[str] = None,
        display_name: Optional[str] = None,
        bio: Optional[str] = None,
        public_summary_enabled: Optional[bool] = None,
    ) -> dict:
        pk = _sanitize_username(username)
        existing = self._get_or_create_default_sync(pk)
        if visibility is not None:
            existing["profile_visibility"] = _normalize_visibility(visibility)
        if display_name is not None:
            existing["display_name"] = _normalize_display_name(
                display_name, existing.get("nickname") or pk
            )
        if bio is not None:
            existing["bio"] = _normalize_bio(bio)
        if public_summary_enabled is not None:
            existing["public_training_summary_enabled"] = bool(public_summary_enabled)
        existing["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(existing))
        return existing

    async def update_profile(
        self,
        username: str,
        visibility: Optional[str] = None,
        display_name: Optional[str] = None,
        bio: Optional[str] = None,
        public_summary_enabled: Optional[bool] = None,
    ) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._update_profile_sync(
                username, visibility, display_name, bio, public_summary_enabled
            ),
        )

    def _update_avatar_sync(self, username: str, avatar_url: Optional[str]) -> dict:
        pk = _sanitize_username(username)
        existing = self._get_or_create_default_sync(pk)
        existing["avatar_url"] = avatar_url or None
        existing["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(existing))
        return existing

    async def update_avatar(self, username: str, avatar_url: Optional[str]) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._update_avatar_sync(username, avatar_url)
        )

    def _update_ranking_location_sync(
        self, username: str, country: Optional[str], region: Optional[str]
    ) -> dict:
        pk = _sanitize_username(username)
        existing = self._get_or_create_default_sync(pk)
        existing["ranking_country"] = (
            country.strip() if isinstance(country, str) and country.strip() else None
        )
        existing["ranking_region"] = (
            region.strip() if isinstance(region, str) and region.strip() else None
        )
        existing["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(existing))
        return existing

    async def update_ranking_location(
        self, username: str, country: Optional[str], region: Optional[str]
    ) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._update_ranking_location_sync(username, country, region)
        )

    def _update_age_class_sync(self, username: str, age_class: str) -> dict:
        pk = _sanitize_username(username)
        existing = self._get_or_create_default_sync(pk)
        existing["age_class"] = _normalize_age_class(age_class)
        existing["updated_at"] = _now_iso()
        self.table.put_item(Item=_to_dynamo(existing))
        return existing

    async def update_age_class(self, username: str, age_class: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._update_age_class_sync(username, age_class)
        )


def make_avatar_object_key(owner: str, file_ext: str) -> str:
    safe_owner = re.sub(r"[^a-z0-9_-]", "_", (owner or "anon").lower())[:64]
    safe_ext = (file_ext or "jpg").lstrip(".").lower()
    if safe_ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        safe_ext = "jpg"
    return f"profiles/{safe_owner}/avatars/{uuid.uuid4().hex}.{safe_ext}"
