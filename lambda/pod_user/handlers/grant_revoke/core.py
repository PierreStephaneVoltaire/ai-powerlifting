from __future__ import annotations

import asyncio
import logging
import re

from boto3.dynamodb.conditions import Key

from .._shared.requests_table import _get_table, _now_iso, _to_dynamo, build_pk, normalize_grant

logger = logging.getLogger(__name__)

MAPPED_PK_RE = re.compile(r"^[A-Za-z0-9:_#-]{1,128}$")


async def grant_revoke(args: dict) -> dict:
    """Revoke a previously issued grant.

    Args:
        athlete_mapped_pk: the athlete who owns the grant
        sk: the SK of the grant to revoke (as returned by grant_list)
        revoked_by: the actor revoking (athlete, or delegated coach/handler)
    """
    athlete_mapped_pk = str(args.get("athlete_mapped_pk") or "").strip()
    sk = str(args.get("sk") or "").strip()
    revoked_by = str(args.get("revoked_by") or athlete_mapped_pk).strip()
    if not MAPPED_PK_RE.match(athlete_mapped_pk):
        raise ValueError("invalid_athlete_mapped_pk")
    if not sk:
        raise ValueError("invalid_sk")

    table = _get_table()
    pk = build_pk(athlete_mapped_pk)

    def _update():
        return table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=(
                "SET revoked_at = :now, revoked_by = :by, last_edited_by = :by, updated_at = :now"
            ),
            ExpressionAttributeValues=_to_dynamo(
                {":now": _now_iso(), ":by": revoked_by}
            ),
            ReturnValues="ALL_NEW",
        )

    resp = await asyncio.get_running_loop().run_in_executor(None, _update)
    item = resp.get("Attributes")
    if not item:
        return {"error": "GRANT_NOT_FOUND"}
    return normalize_grant(item)
