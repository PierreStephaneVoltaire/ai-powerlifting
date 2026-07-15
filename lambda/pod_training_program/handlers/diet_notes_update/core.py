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
        logger.info("[DietNotesUpdate] DynamoDB table initialised: %s", table_name)
    return _table


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _resolve_program_sk_sync(table, pk: str, version: str) -> str:
    if version == "current":
        pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


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


async def diet_notes_update(args: dict) -> dict:
    """Replace the diet notes array for a program version.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              and required `notes` (list of note dicts).
    """
    table = _get_table()
    pk = _resolve_pk(args)
    version = args.get("version") or "current"
    notes = args.get("notes")
    if not isinstance(notes, list):
        raise ValueError("notes must be a list")
    now = datetime.now(timezone.utc).isoformat()

    def _sync():
        sk = _resolve_program_sk_sync(table, pk, version)
        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression="SET diet_notes = :notes, #meta.updated_at = :now",
            ExpressionAttributeNames={"#meta": "meta"},
            ExpressionAttributeValues={
                ":notes": _to_dynamo(notes),
                ":now": now,
            },
        )
        return {
            "version": version,
            "sk": sk,
            "notes": notes,
            "updated_at": now,
        }

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)
