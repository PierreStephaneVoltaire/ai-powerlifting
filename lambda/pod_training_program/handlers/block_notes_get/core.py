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
        logger.info("[BlockNotesTools] DynamoDB table initialised: %s", table_name)
    return _table


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _resolve_program_sk_sync(table, pk: str, version: str) -> str:
    """Resolve a program sk from a version label.

    "current" reads the program#current pointer's ref_sk; otherwise builds
    program#{version}.
    """
    if version == "current":
        pointer = table.get_item(Key={"pk": pk, "sk": "program#current"}).get("Item")
        if pointer:
            return pointer.get("ref_sk", "program#v001")
        return "program#v001"
    return f"program#{version}"


async def block_notes_get(args: dict) -> dict:
    """Get block notes for a program version.

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
            ProjectionExpression="#meta.block_notes, block_notes",
            ExpressionAttributeNames={"#meta": "meta"},
        )
        item = resp.get("Item")
        if not item:
            raise ValueError(f"Program version {version} not found")
        meta = item.get("meta") or {}
        meta_notes = meta.get("block_notes")
        legacy_notes = item.get("block_notes")
        if isinstance(meta_notes, list) and (len(meta_notes) > 0 or not isinstance(legacy_notes, list)):
            notes = meta_notes
        else:
            notes = legacy_notes if isinstance(legacy_notes, list) else []
        return {"version": version, "sk": sk, "block_notes": notes}

    return await asyncio.get_running_loop().run_in_executor(None, _sync)