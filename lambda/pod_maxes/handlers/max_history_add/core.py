from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)

def _get_table():
    region = os.environ.get("AWS_REGION", "ca-central-1")
    table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
    return boto3.resource("dynamodb", region_name=region).Table(table_name)


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
    try:
        date.fromisoformat(str(entry["date"]))
    except ValueError as exc:
        raise ValueError("entry.date must be YYYY-MM-DD") from exc
    if not any(entry.get(key) is not None for key in ("squat_kg", "bench_kg", "deadlift_kg")):
        raise ValueError("At least one lift max is required")
    if entry.get("total_kg") is None:
        entry["total_kg"] = sum(entry.get(key, 0) or 0 for key in ("squat_kg", "bench_kg", "deadlift_kg"))

    def _sync():
        response = table.update_item(
            Key={"pk": pk, "sk": _max_history_sk(version)},
            UpdateExpression="SET entries = list_append(if_not_exists(entries, :empty), :entry), #version = :version, updated_at = :now",
            ExpressionAttributeNames={"#version": "version"},
            ExpressionAttributeValues={":empty": [], ":entry": _to_dynamo([entry]), ":version": version, ":now": datetime.now(timezone.utc).isoformat()},
            ReturnValues="ALL_NEW",
        )
        history = response["Attributes"]
        history["entries"].sort(key=lambda item: item["date"], reverse=True)
        return history

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)
