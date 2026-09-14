from __future__ import annotations

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
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    if start_date:
        date.fromisoformat(str(start_date))
    if end_date:
        date.fromisoformat(str(end_date))
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
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
    item = _sanitize_decimals(item)
    if start_date or end_date:
        item["entries"] = [entry for entry in item.get("entries", []) if (not start_date or entry.get("date", "") >= start_date) and (not end_date or entry.get("date", "") <= end_date)]
    return item
