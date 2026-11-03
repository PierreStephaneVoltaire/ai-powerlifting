from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client

logger = logging.getLogger(__name__)

def _get_table():
    region = os.environ.get("AWS_REGION", "ca-central-1")
    table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
    return dynamodb_resource("dynamodb", region_name=region).Table(table_name)


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


async def max_target_update(args: dict) -> dict:
    """Replace the target maxes (squat/bench/deadlift) for a program version.

    Args:
        args: dict with optional `pk`, `version` (defaults to "current"),
              and `squat_kg`, `bench_kg`, `deadlift_kg` (numbers).
              `total_kg` is recomputed as the sum of the three lifts.
    """
    pk = _resolve_pk(args)
    version = args.get("version") or "current"
    try:
        if not all(args.get(key) is not None for key in ("squat_kg", "bench_kg", "deadlift_kg")):
            raise ValueError
        squat = float(args["squat_kg"])
        bench = float(args["bench_kg"])
        dl = float(args["deadlift_kg"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "squat_kg, bench_kg, deadlift_kg must be numeric"
        ) from exc
    total = squat + bench + dl
    from services.lib.program_store import ProgramStore
    store = ProgramStore(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), pk, os.environ.get("AWS_REGION", "ca-central-1"))
    if version != "current":
        store._selected_program_sk = f"program#{version}"
    committed = await store.update_meta_fields({
        "target_squat_kg": squat,
        "target_bench_kg": bench,
        "target_dl_kg": dl,
        "target_total_kg": total,
    }, args.get("expected_revision"), args.get("idempotency_key"))
    meta = committed.get("meta") or {}
    return _sanitize_decimals({
        "version": version,
        "sk": committed["sk"],
        "squat_kg": meta.get("target_squat_kg"),
        "bench_kg": meta.get("target_bench_kg"),
        "deadlift_kg": meta.get("target_dl_kg"),
        "total_kg": meta.get("target_total_kg"),
        "updated_at": committed["updated_at"],
        "revision": committed.get("revision"),
    })
