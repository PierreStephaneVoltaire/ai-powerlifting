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
        table_name = os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[SessionList] DynamoDB table initialised: %s", table_name)
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


def _to_int(value, default: int = 0) -> int:
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


async def session_list(args: dict) -> dict:
    """List the most recent sessions for a user.

    Args:
        args: dict with optional `pk` and optional `limit` (default 50, max 200).
              Returns session summaries sorted by date desc, then by sk desc.
    """
    table = _get_table()
    pk = _resolve_pk(args)
    try:
        limit = int(args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(200, limit))

    def _sync() -> dict:
        items: List[dict] = []
        last_key = None
        while True:
            query_kwargs = {
                "KeyConditionExpression": Key("pk").eq(pk),
                "ScanIndexForward": False,
            }
            if last_key:
                query_kwargs["ExclusiveStartKey"] = last_key
            resp = table.query(**query_kwargs)
            for item in resp.get("Items", []) or []:
                item = _sanitize_decimals(item)
                date = item.get("date") or ""
                week = _to_int(item.get("week_number", 0))
                block = item.get("block", "current") or "current"
                items.append(
                    {
                        "sk": item.get("sk"),
                        "date": date,
                        "week_number": week,
                        "block": block,
                        "label": item.get("label", ""),
                        "name": item.get("name", ""),
                        "status": item.get("status", ""),
                        "completed": bool(item.get("completed", False)),
                        "exercise_count": len(item.get("exercises", []) or []),
                    }
                )
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        items.sort(
            key=lambda s: (str(s.get("date", "")), str(s.get("sk", ""))),
            reverse=True,
        )
        return {
            "sessions": items[:limit],
            "count": len(items[:limit]),
            "total": len(items),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
