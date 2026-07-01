from __future__ import annotations

import asyncio
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
        logger.info("[MaxHistoryAdd] DynamoDB table initialised: %s", table_name)
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


def _max_history_sk(version: str) -> str:
    return f"max_history#{version}"


def _get_history_sync(table, pk: str, version: str) -> dict:
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


async def max_history_add(args: dict) -> dict:
    """Append a max entry to the max history for a program version.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              and required `entry` (with `date` and `squat_kg`, `bench_kg`,
              `deadlift_kg`, optional `total_kg`).
    """
    table = _get_table()
    pk = _resolve_pk(args)
    version = args.get("version") or "current"
    entry = dict(args.get("entry") or {})
    if not entry and args.get("date"):
        entry = {k: v for k, v in args.items() if k not in {"pk", "version"}}

    if not entry.get("date"):
        raise ValueError("entry.date (or args.date) is required (YYYY-MM-DD)")

    def _sync():
        history = _get_history_sync(table, pk, version)
        entries = list(history.get("entries", []) or [])
        entries.append(entry)
        entries.sort(key=lambda e: str(e.get("date", "") or ""), reverse=True)
        history["entries"] = entries
        history["version"] = version
        history["updated_at"] = datetime.now(timezone.utc).isoformat()
        table.put_item(Item=_to_dynamo(history))
        return history

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)
