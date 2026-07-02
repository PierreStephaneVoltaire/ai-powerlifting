from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)

_table = None


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get(
            "IF_ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"
        )
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[AnalysisCacheMarkDirty] DynamoDB table initialised: %s", table_name)
    return _table


def _resolve_user_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _to_dynamo(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _sanitize_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


async def analysis_cache_mark_dirty(args: dict) -> dict:
    """Mark a user's markdown export as dirty so the next read regenerates it.

    Args:
        args: dict with optional `pk` and optional `block_key` (defaults to "current"),
              and optional `reason` (free text). Writes a row with
              sk = ``markdown_export_dirty#<block_key>`` under pk = ``analysis#<user_pk>``.
    """
    table = _get_table()
    user_pk = _resolve_user_pk(args)
    block_key = args.get("block_key") or "current"
    reason = args.get("reason") or ""
    now = datetime.now(timezone.utc).isoformat()
    pk = f"analysis#{user_pk}"
    sk = f"markdown_export_dirty#{block_key}"

    def _sync():
        item = _to_dynamo({
            "pk": pk,
            "sk": sk,
            "dirty_at": now,
            "updated_at": now,
            "reason": str(reason),
            "block_key": block_key,
        })
        table.put_item(Item=item)
        return {"pk": pk, "sk": sk, "block_key": block_key, "reason": reason, "dirty_at": now}

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
