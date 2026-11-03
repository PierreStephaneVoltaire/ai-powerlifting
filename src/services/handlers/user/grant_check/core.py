from __future__ import annotations

import asyncio
import logging
import re

from boto3.dynamodb.conditions import Key

from .._shared.requests_table import _get_table, build_pk, is_active, normalize_grant

logger = logging.getLogger(__name__)

MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")


async def grant_check(args: dict) -> dict:
    """Check whether an actor has an active grant on an athlete.

    Args:
        athlete_mapped_pk: the athlete whose data the actor wants to access
        actor_mapped_pk: the actor (coach/handler) requesting access
        grant_type: "coach" | "handler" | None (any)
        scope: "read" | "write" | None (any)
        tied_competition_id: optional competition id the access must cover
            (returns true only if the grant is open or lists this comp)

    Returns: { allowed: bool, grant?: dict, reason: string }
    """
    athlete_mapped_pk = str(args.get("athlete_mapped_pk") or "").strip()
    actor_mapped_pk = str(args.get("actor_mapped_pk") or "").strip()
    grant_type = (args.get("grant_type") or "").strip() or None
    scope = (args.get("scope") or "").strip() or None
    tied_competition_id = (args.get("tied_competition_id") or "").strip() or None

    if not MAPPED_PK_RE.match(athlete_mapped_pk):
        raise ValueError("invalid_athlete_mapped_pk")
    if not MAPPED_PK_RE.match(actor_mapped_pk):
        raise ValueError("invalid_actor_mapped_pk")
    if athlete_mapped_pk == actor_mapped_pk:
        return {"allowed": True, "reason": "self"}

    table = _get_table()

    def _fetch():
        items = table.query(KeyConditionExpression=Key("pk").eq(build_pk(athlete_mapped_pk)))[
            "Items"
        ]
        return [normalize_grant(i) for i in items]

    rows = await asyncio.get_running_loop().run_in_executor(None, _fetch)
    for row in rows:
        if not is_active(row):
            continue
        if row.get("grantee_mapped_pk") != actor_mapped_pk:
            continue
        if grant_type and row.get("grant_type") != grant_type:
            continue
        if scope:
            row_scope = row.get("scope") or "read"
            if scope == "write" and row_scope != "write":
                continue
        if tied_competition_id:
            tied = row.get("tied_competition_ids") or []
            if tied and tied_competition_id not in tied:
                continue
        return {"allowed": True, "grant": row, "reason": "active_grant"}
    return {"allowed": False, "reason": "no_active_grant"}
