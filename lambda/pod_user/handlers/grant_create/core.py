from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from boto3.dynamodb.conditions import Key

from .._shared.requests_table import (
    GRANT_TYPES,
    SCOPES,
    _get_table,
    _now_iso,
    _to_dynamo,
    build_pk,
    build_sk,
    is_active,
    normalize_grant,
)

logger = logging.getLogger(__name__)

MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")
NICKNAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")
EXPIRY_TAIL_DAYS = 7  # FEAT-4.2: grant expires max(tied competition dates) + 7d
TIE_DURATION_DEFAULT_DAYS = 60  # for open-ended grants (no tied competitions)


def _validate_args(args: dict) -> tuple[Optional[str], Optional[dict]]:
    athlete_mapped_pk = str(args.get("athlete_mapped_pk") or "").strip()
    grantee_mapped_pk = str(args.get("grantee_mapped_pk") or "").strip()
    grant_type = str(args.get("grant_type") or "coach").strip().lower()
    scope = str(args.get("scope") or "read").strip().lower()
    tied_competition_ids = args.get("tied_competition_ids") or []
    tied_competition_dates = args.get("tied_competition_dates") or {}
    note = str(args.get("note") or "").strip()[:280]
    created_by = str(args.get("created_by") or athlete_mapped_pk).strip()
    grantee_nickname = str(args.get("grantee_nickname") or "").strip()
    grantee_discord_id = str(args.get("grantee_discord_id") or "").strip()
    grantee_authentik_sub = str(args.get("grantee_authentik_sub") or "").strip()

    if not MAPPED_PK_RE.match(athlete_mapped_pk):
        return "invalid_athlete_mapped_pk", None
    if not MAPPED_PK_RE.match(grantee_mapped_pk):
        return "invalid_grantee_mapped_pk", None
    if athlete_mapped_pk == grantee_mapped_pk:
        return "cannot_grant_to_self", None
    if grant_type not in GRANT_TYPES:
        return "invalid_grant_type", None
    if scope not in SCOPES:
        return "invalid_scope", None
    if not isinstance(tied_competition_ids, list):
        return "invalid_tied_competition_ids", None
    if not isinstance(tied_competition_dates, dict):
        return "invalid_tied_competition_dates", None
    if grantee_nickname and not NICKNAME_RE.match(grantee_nickname):
        return "invalid_grantee_nickname", None

    tied_competition_ids = [str(c) for c in tied_competition_ids if str(c).strip()][:32]

    if tied_competition_dates:
        latest = None
        for d in tied_competition_dates.values():
            try:
                parsed = datetime.fromisoformat(str(d).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if latest is None or parsed > latest:
                    latest = parsed
            except Exception:
                continue
        if latest is None:
            return "invalid_tied_competition_dates", None
        expires_at_dt = latest + timedelta(days=EXPIRY_TAIL_DAYS)
    else:
        expires_at_dt = datetime.now(timezone.utc) + timedelta(days=TIE_DURATION_DEFAULT_DAYS)

    now = _now_iso()
    grant = {
        "pk": build_pk(athlete_mapped_pk),
        "athlete_mapped_pk": athlete_mapped_pk,
        "athlete_nickname": str(args.get("athlete_nickname") or "").strip(),
        "grantee_mapped_pk": grantee_mapped_pk,
        "grantee_nickname": grantee_nickname,
        "grantee_discord_id": grantee_discord_id,
        "grantee_authentik_sub": grantee_authentik_sub,
        "grant_type": grant_type,
        "scope": scope,
        "tied_competition_ids": tied_competition_ids,
        "expires_at": expires_at_dt.isoformat(),
        "revoked_at": None,
        "revoked_by": None,
        "created_by": created_by,
        "note": note,
        "last_edited_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    grant["sk"] = build_sk(grantee_mapped_pk, now, grant_type)
    return None, grant


async def grant_create(args: dict) -> dict:
    """Issue a new grant from an athlete to a coach or handler.

    The athlete (or a delegated coach/handler with grants:write on grants) is
    identified by `athlete_mapped_pk`. The grantee is `grantee_mapped_pk`.

    Returns the persisted grant. Raises ValueError on validation failure or on
    GRANT_LIMIT_REACHED when an active grant of the same type already exists.
    """
    err, grant = _validate_args(args)
    if err:
        raise ValueError(err)

    table = _get_table()

    def _check_existing():
        pk = grant["pk"]
        existing = table.query(KeyConditionExpression=Key("pk").eq(pk))["Items"]
        for item in existing:
            norm = normalize_grant(item)
            if norm["grant_type"] == grant["grant_type"] and is_active(norm):
                return norm
        return None

    existing = await asyncio.get_running_loop().run_in_executor(None, _check_existing)
    if existing:
        return {
            "error": "GRANT_LIMIT_REACHED",
            "message": f"An active {grant['grant_type']} grant already exists for this athlete.",
            "existing": existing,
        }

    def _put():
        table.put_item(Item=_to_dynamo(grant))

    await asyncio.get_running_loop().run_in_executor(None, _put)
    return normalize_grant(grant)
