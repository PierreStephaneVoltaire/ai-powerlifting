from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)

_table = None


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[MaxHistoryGet] DynamoDB table initialised: %s", table_name)
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


def _max_history_sk(version: str) -> str:
    return f"max_history#{version}"


async def max_history_get(args: dict) -> dict:
    """Get the max history for a program version.

    Args:
        args: dict with optional `pk` and `version` (defaults to "current").
    """
    table = _get_table()
    pk = _resolve_pk(args)
    version = args.get("version") or "current"
    sk = _max_history_sk(version)
    resp = table.get_item(Key={"pk": pk, "sk": sk})
    item = resp.get("Item")
    if not item:
        return {
            "pk": pk,
            "sk": sk,
            "version": version,
            "entries": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    return _sanitize_decimals(item)
