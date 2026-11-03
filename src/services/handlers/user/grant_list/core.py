from __future__ import annotations

import asyncio
import logging
import re

from boto3.dynamodb.conditions import Key

from .._shared.requests_table import _get_table, build_pk, is_active, normalize_grant

logger = logging.getLogger(__name__)

MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")


async def grant_list(args: dict) -> dict:
    """List grants for an athlete, or grants held by a grantee across athletes.

    Args:
        athlete_mapped_pk: optional. If provided, returns grants issued by that
            athlete (the ones an athlete manages on their own profile).
        grantee_mapped_pk: optional. If provided, returns active grants held by
            this grantee across all athletes.
        include_inactive: defaults to False; if True, also returns revoked
            and expired grants.

    Returns: { active: [...], inactive: [...], total: N }
    """
    athlete_mapped_pk = (args.get("athlete_mapped_pk") or "").strip() or None
    grantee_mapped_pk = (args.get("grantee_mapped_pk") or "").strip() or None
    include_inactive = bool(args.get("include_inactive"))

    if athlete_mapped_pk and not MAPPED_PK_RE.match(athlete_mapped_pk):
        raise ValueError("invalid_athlete_mapped_pk")
    if grantee_mapped_pk and not MAPPED_PK_RE.match(grantee_mapped_pk):
        raise ValueError("invalid_grantee_mapped_pk")
    if not athlete_mapped_pk and not grantee_mapped_pk:
        raise ValueError("athlete_or_grantee_required")

    table = _get_table()

    def _fetch():
        if athlete_mapped_pk:
            items = table.query(KeyConditionExpression=Key("pk").eq(build_pk(athlete_mapped_pk)))[
                "Items"
            ]
            if not grantee_mapped_pk:
                return [normalize_grant(i) for i in items]
            return [
                normalize_grant(i)
                for i in items
                if normalize_grant(i).get("grantee_mapped_pk") == grantee_mapped_pk
            ]
        # grantee-only: scan the whole table (low cardinality table, MVP-OK;
        # production should add a GSI keyed on grantee_mapped_pk).
        resp = table.scan()
        items = resp.get("Items") or []
        results = []
        for raw in items:
            norm = normalize_grant(raw)
            if norm.get("grantee_mapped_pk") == grantee_mapped_pk:
                results.append(norm)
        return results

    rows = await asyncio.get_running_loop().run_in_executor(None, _fetch)
    active = [r for r in rows if is_active(r)]
    inactive = [r for r in rows if not is_active(r)]
    if not include_inactive:
        return {"active": active, "total": len(active), "inactive": []}
    return {"active": active, "inactive": inactive, "total": len(rows)}
