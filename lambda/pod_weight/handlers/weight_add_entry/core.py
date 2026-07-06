from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

_table = None


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[WeightTools] DynamoDB table initialised: %s", table_name)
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


def _to_dynamo(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _weight_log_sk(version: str) -> str:
    return f"weight_log#{version}"


def _get_log_sync(table, pk: str, version: str) -> dict:
    sk = _weight_log_sk(version)
    resp = table.get_item(Key={"pk": pk, "sk": sk})
    item = resp.get("Item")
    if not item:
        return {
            "pk": pk,
            "sk": sk,
            "entries": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    return _sanitize_decimals(item)


async def weight_add_entry(args: dict) -> dict:
    """Add (or replace by date) a weight entry in the weight log.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              and required `entry` ({date, ...weight fields}).
    """
    import asyncio

    table = _get_table()
    pk = _resolve_pk(args)
    version = args.get("version") or "current"
    entry = args.get("entry") or {}

    def _sync():
        log = _get_log_sync(table, pk, version)
        entries = list(log.get("entries", []) or [])
        existing_index = None
        for i, e in enumerate(entries):
            if e.get("date") == entry.get("date"):
                existing_index = i
                break
        if existing_index is not None:
            entries[existing_index] = entry
        else:
            entries.append(entry)
        entries.sort(key=lambda e: str(e.get("date", "") or ""), reverse=True)
        log["entries"] = entries
        log["updated_at"] = datetime.now(timezone.utc).isoformat()
        table.put_item(Item=_to_dynamo(log))
        return log

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)