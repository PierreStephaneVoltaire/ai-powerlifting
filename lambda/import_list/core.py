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
        logger.info("[ImportList] DynamoDB table initialised: %s", table_name)
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


async def import_list(args: dict) -> dict:
    """List import summaries for a user.

    Args:
        args: dict with optional `pk` and optional `limit` (default 100, max 500).
              Returns import rows (sk begins_with "import#") sorted newest first
              by sk.
    """
    table = _get_table()
    pk = _resolve_pk(args)
    try:
        limit = int(args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(500, limit))

    def _sync() -> dict:
        items: List[dict] = []
        last_key = None
        while True:
            query_kwargs = {
                "KeyConditionExpression": Key("pk").eq(pk)
                & Key("sk").begins_with("import#"),
                "ScanIndexForward": False,
            }
            if last_key:
                query_kwargs["ExclusiveStartKey"] = last_key
            resp = table.query(**query_kwargs)
            for item in resp.get("Items", []) or []:
                item = _sanitize_decimals(item)
                items.append(
                    {
                        "sk": item.get("sk"),
                        "id": item.get("id", ""),
                        "filename": item.get("filename", ""),
                        "source": item.get("source", ""),
                        "format": item.get("format", ""),
                        "status": item.get("status", ""),
                        "classification": item.get("classification", ""),
                        "row_count": _to_int(item.get("row_count", 0)),
                        "session_count": _to_int(item.get("session_count", 0)),
                        "created_at": item.get("created_at", ""),
                        "updated_at": item.get("updated_at", ""),
                    }
                )
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return {
            "imports": items[:limit],
            "count": len(items[:limit]),
            "total": len(items),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
