from __future__ import annotations

import uuid

import asyncio
import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from botocore.exceptions import ClientError
from services.lib.program_store import ProgramRevisionConflictError, require_mutation_envelope

logger = logging.getLogger(__name__)

def _get_table():
    region = os.environ.get("AWS_REGION", "ca-central-1")
    table_name = os.environ.get("IF_HEALTH_TABLE_NAME", "if-health")
    return dynamodb_resource("dynamodb", region_name=region).Table(table_name)


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

def _marker_sk(actor_pk: str, version: str, key: str) -> str:
    import hashlib
    return f"max-history-idempotency#{hashlib.sha256(f'{actor_pk}:{version}:{key}'.encode()).hexdigest()[:32]}"

def _payload_hash(actor_pk: str, version: str, entry: dict) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps({"actor_pk": actor_pk, "version": version, "entry": entry}, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()

ENTRY_FIELDS = {"id", "entry_id", "date", "squat_kg", "bench_kg", "deadlift_kg", "total_kg", "bodyweight_kg", "context"}


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
    expected_revision, idempotency_key = require_mutation_envelope(args.get("expected_revision"), args.get("idempotency_key"))
    raw_entry = dict(args.get("entry") or {})
    if not raw_entry and args.get("date"):
        raw_entry = args
    entry = {key: value for key, value in raw_entry.items() if key in ENTRY_FIELDS}

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

    import hashlib
    actor_pk = str(args.get("_person_pk") or pk)
    entry.setdefault("id", hashlib.sha256(f"{actor_pk}:{version}:{idempotency_key}".encode()).hexdigest()[:24] if idempotency_key else uuid.uuid4().hex[:24])
    def _sync():
        current = table.get_item(Key={"pk": pk, "sk": _max_history_sk(version)}, ConsistentRead=True).get("Item") or {"entries": []}
        entries = [item for item in (current.get("entries") or []) if item.get("id") != entry["id"]] + [_to_dynamo(entry)]
        entries.sort(key=lambda item: item["date"], reverse=True)
        result = {**current, "pk": pk, "sk": _max_history_sk(version), "version": version, "entries": entries, "updated_at": datetime.now(timezone.utc).isoformat()}
        result.pop("revision", None)
        table.put_item(Item=_to_dynamo(result))
        return result

    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    return _sanitize_decimals(result)
