"""Shared helpers for the grant_* handlers (grant store).

The grant store lives in the `if-powerlifting-requests` DynamoDB table.

Key shape:
  pk = "Grant#{athlete_mapped_pk}"  (the athlete who issued the grant)
  sk = "Grantee#{grantee_mapped_pk}#{granted_at_iso}#{grant_type}"
  attrs:
    athlete_mapped_pk
    athlete_nickname
    grantee_mapped_pk
    grantee_nickname
    grantee_discord_id
    grantee_authentik_sub
    grant_type        "coach" | "handler"
    scope             "read" | "write"
    tied_competition_ids   list[str]
    expires_at        ISO8601
    revoked_at        ISO8601 | None
    revoked_by        mapped_pk | None
    created_by        mapped_pk  (always the athlete for new grants)
    note              str
    last_edited_by    mapped_pk
    created_at        ISO8601
    updated_at        ISO8601
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_table = None
GRANT_TYPES = ("coach", "handler")
SCOPES = ("read", "write")


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[GrantsTools] Requests table initialised: %s", table_name)
    return _table


def _sanitize_decimals(obj: Any) -> Any:
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_pk(athlete_mapped_pk: str) -> str:
    return f"Grant#{athlete_mapped_pk}"


def build_sk(grantee_mapped_pk: str, granted_at_iso: str, grant_type: str) -> str:
    return f"Grantee#{grantee_mapped_pk}#{granted_at_iso}#{grant_type}"


def normalize_grant(item: dict) -> dict:
    raw = _sanitize_decimals(item)
    return {
        "pk": raw.get("pk"),
        "sk": raw.get("sk"),
        "athlete_mapped_pk": str(raw.get("athlete_mapped_pk") or ""),
        "athlete_nickname": str(raw.get("athlete_nickname") or ""),
        "grantee_mapped_pk": str(raw.get("grantee_mapped_pk") or ""),
        "grantee_nickname": str(raw.get("grantee_nickname") or ""),
        "grantee_discord_id": str(raw.get("grantee_discord_id") or ""),
        "grantee_authentik_sub": str(raw.get("grantee_authentik_sub") or ""),
        "grant_type": str(raw.get("grant_type") or ""),
        "scope": str(raw.get("scope") or "read"),
        "tied_competition_ids": list(raw.get("tied_competition_ids") or []),
        "expires_at": str(raw.get("expires_at") or ""),
        "revoked_at": raw.get("revoked_at"),
        "revoked_by": raw.get("revoked_by"),
        "created_by": str(raw.get("created_by") or ""),
        "note": str(raw.get("note") or ""),
        "last_edited_by": str(raw.get("last_edited_by") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def is_active(grant: dict, now: Optional[datetime] = None) -> bool:
    if grant.get("revoked_at"):
        return False
    expires_at = grant.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except Exception:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > (now or datetime.now(timezone.utc))
