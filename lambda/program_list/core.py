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
        table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[ProgramList] DynamoDB table initialised: %s", table_name)
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


async def program_list(args: dict) -> dict:
    """List program versions for a user, newest first.

    Args:
        args: dict with optional `pk` and optional `include_archived` (default False).
    """
    table = _get_table()
    pk = _resolve_pk(args)
    include_archived = bool(args.get("include_archived", False))

    def _sync() -> dict:
        summaries: List[dict] = []
        last_key = None
        while True:
            query_kwargs = {
                "KeyConditionExpression": Key("pk").eq(pk)
                & Key("sk").begins_with("program#v"),
                "ScanIndexForward": False,
            }
            if last_key:
                query_kwargs["ExclusiveStartKey"] = last_key
            resp = table.query(**query_kwargs)
            for item in resp.get("Items", []) or []:
                item = _sanitize_decimals(item)
                meta = item.get("meta") or {}
                archived = bool(meta.get("archived", False))
                if not include_archived and archived:
                    continue
                summaries.append(
                    {
                        "sk": item.get("sk"),
                        "version": int(meta.get("version", 0) or 0)
                        or (int(item.get("sk", "program#v").split("#v")[-1] or 0) if "#v" in str(item.get("sk", "")) else 0),
                        "name": meta.get("name", ""),
                        "description": meta.get("description", ""),
                        "estimated_weeks": meta.get("estimated_weeks"),
                        "days_per_week": meta.get("days_per_week"),
                        "archived": archived,
                        "archived_at": meta.get("archived_at"),
                        "updated_at": meta.get("updated_at", ""),
                        "session_count": len(item.get("sessions", []) or []),
                    }
                )
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        # Sort by version desc as a safety net
        summaries.sort(key=lambda s: int(s.get("version", 0) or 0), reverse=True)
        return {"programs": summaries, "count": len(summaries)}

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
