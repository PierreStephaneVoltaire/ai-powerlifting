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
        logger.info("[MaxTargetGet] DynamoDB table initialised: %s", table_name)
    return _table


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _resolve_program_sk_sync(table, pk: str, version: str) -> str:
    """Resolve a program sk from a version label."""
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


async def max_target_get(args: dict) -> dict:
    """Get the target maxes (squat/bench/deadlift/total) for a program version.

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
            ProjectionExpression="#meta.target_squat_kg, #meta.target_bench_kg, #meta.target_dl_kg, #meta.target_total_kg",
            ExpressionAttributeNames={"#meta": "meta"},
        )
        item = resp.get("Item")
        if not item:
            raise ValueError(f"Program version {version} not found")
        meta = item.get("meta") or {}
        return {
            "version": version,
            "sk": sk,
            "squat_kg": meta.get("target_squat_kg"),
            "bench_kg": meta.get("target_bench_kg"),
            "deadlift_kg": meta.get("target_dl_kg"),
            "total_kg": meta.get("target_total_kg"),
        }

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)
