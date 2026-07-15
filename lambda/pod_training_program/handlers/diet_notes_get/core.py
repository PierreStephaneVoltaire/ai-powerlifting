from __future__ import annotations

import asyncio
import logging
import os
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
        logger.info("[DietNotesGet] DynamoDB table initialised: %s", table_name)
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


async def diet_notes_get(args: dict) -> dict:
    """Get the diet notes array for a program version.

    Args:
        args: dict with optional `pk` and `version` (defaults to "current").
    """
    table = _get_table()
    pk = _resolve_pk(args)
    version = args.get("version") or "current"

    def _sync():
        sk = _resolve_program_sk_sync(table, pk, version)
        resp = table.get_item(
            Key={"pk": pk, "sk": sk},
            ProjectionExpression="diet_notes",
        )
        item = resp.get("Item")
        if not item:
            raise ValueError(f"Program version {version} not found")
        notes = item.get("diet_notes") or []
        if not isinstance(notes, list):
            notes = []
        return {"version": version, "sk": sk, "notes": notes}

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)
