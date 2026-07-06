from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_table = None


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info(
            "[GlossaryListTerms] DynamoDB table initialised: %s", table_name
        )
    return _table


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _sanitize_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


async def glossary_list_terms(args: dict) -> dict:
    """List glossary exercise terms for a user.

    Scans ``if-health-templates`` (or whichever templates table is configured)
    for rows under pk=<user> with sk beginning with ``glossary#``, then flattens
    the canonical exercises list into a list of term summaries.

    Args:
        args: dict with optional `pk`.
    """
    table = _get_table()
    pk = _resolve_pk(args)

    def _sync() -> dict:
        terms: List[dict] = []
        last_key = None
        while True:
            scan_kwargs: dict = {
                "FilterExpression": "begins_with(sk, :prefix)",
                "ExpressionAttributeValues": {":prefix": "glossary#"},
            }
            if last_key:
                scan_kwargs["ExclusiveStartKey"] = last_key
            # Use Query when pk is the partition key; fall back to Scan for the
            # templates table (which has pk + sk + GSI shapes across versions).
            try:
                resp = table.query(
                    KeyConditionExpression=Key("pk").eq(pk)
                    & Key("sk").begins_with("glossary#")
                )
            except Exception:
                resp = table.scan(**scan_kwargs)
            for item in resp.get("Items", []) or []:
                item = _sanitize_decimals(item)
                exercises = item.get("exercises") or []
                if isinstance(exercises, list):
                    for ex in exercises:
                        if not isinstance(ex, dict):
                            continue
                        terms.append(
                            {
                                "sk": item.get("sk"),
                                "id": ex.get("id"),
                                "name": ex.get("name", ""),
                                "description": ex.get("description", ""),
                                "primary_muscles": ex.get("primary_muscles", []),
                                "secondary_muscles": ex.get("secondary_muscles", []),
                                "tertiary_muscles": ex.get("tertiary_muscles", []),
                                "archived": bool(ex.get("archived", False)),
                                "e1rm_kg": ex.get("e1rm_estimate", {}).get("value_kg")
                                if isinstance(ex.get("e1rm_estimate"), dict)
                                else None,
                            }
                        )
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        terms.sort(key=lambda t: str(t.get("name", "")).lower())
        return {"terms": terms, "count": len(terms)}

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
