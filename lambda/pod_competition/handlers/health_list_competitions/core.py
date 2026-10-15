"""User-scoped competition reads/writes against the if-powerlifting-user-competitions
DynamoDB table. The master-sync lambda seeds one item per (user, master_competition)
when the master record changes; this handler is the read + patch surface for the
backend (and the agent, when it needs to look at one user at a time).

Items are keyed pk=<mapped_pk>, sk="COMP#<master_id>". Each item carries the master
fields copied at sync time plus user-owned fields (user_status, weight_class_kg,
body_weight_kg, results, post_meet_report, ...).
"""
from __future__ import annotations

import logging
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

from block_scope import active_block_id_for, in_block
from competition_entries import participation_date

from .config import (
    AWS_REGION,
    HEALTH_PROGRAM_PK,
    POWERLIFTING_USER_COMPETITIONS_TABLE,
)

logger = logging.getLogger(__name__)

_table = None


class CompetitionConflictError(Exception):
    def __init__(self, expected_revision: int, current_revision: int, current_record: dict | None):
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        self.current_record = current_record
        super().__init__(f"revision conflict: expected {expected_revision}, current {current_revision}")


def _transaction_was_cancelled(exc: Exception) -> bool:
    if exc.__class__.__name__ == "TransactionCanceledException":
        return True
    return isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") == "TransactionCanceledException"


def _invalidate_analysis_cache(pk: str) -> None:
    try:
        from cache_invalidation import invalidate_analysis_caches
        invalidate_analysis_caches(
            pk,
            os.getenv("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"),
            os.getenv("AWS_REGION", AWS_REGION),
        )
    except Exception as exc:
        logger.warning("competition analysis cache invalidation failed: %s", exc)


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(
            POWERLIFTING_USER_COMPETITIONS_TABLE
        )
    return _table


def _from_item(item: Optional[dict]) -> Optional[dict]:
    if item is None:
        return None
    out: dict = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, dict):
            out[k] = _from_item(v)
        elif isinstance(v, list):
            out[k] = [_from_item(x) if isinstance(x, dict) else (float(x) if isinstance(x, Decimal) else x) for x in v]
        else:
            out[k] = v
    return out


def _to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    return value


_MUTABLE_FIELDS = {
    "units",
    "user_status",
    "weight_class_kg",
    "body_weight_kg",
    "targets",
    "results",
    "post_meet_report",
    "hotel_required",
    "counts_toward_federation_ids",
    "between_comp_plan",
    "comp_day_protocol",
    "decision_date",
    "attempt_selection",
    "attempt_strategy_mode",
    "qualifying_standard_id",
    "qualifying_total_kg",
    "projected_at_t_minus_1w",
    "projection_snapshot_date",
    "notes",
}


def _mutation_envelope(args: dict) -> tuple[int, str]:
    expected = args.get("expected_revision")
    key = args.get("idempotency_key")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError("expected_revision must be a nonnegative integer")
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise ValueError("idempotency_key must be a nonempty string")
    return expected, key.strip()


def _payload_hash(operation: str, master_id: str, payload: dict) -> str:
    body = {"operation": operation, "master_id": master_id, "payload": payload}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _attempt_id(master_id: str, lift: str, attempt_number: int) -> str:
    return f"{master_id}:{lift}:{attempt_number}"


def _normalise_report(master_id: str, incoming: Any, existing: Any) -> dict:
    if not isinstance(incoming, dict):
        raise ValueError("post_meet_report must be an object")
    previous = existing if isinstance(existing, dict) else {}
    previous_attempts = previous.get("attempts") if isinstance(previous.get("attempts"), list) else []
    by_id: dict[str, dict] = {}
    by_position: dict[tuple[str, int], str] = {}
    for raw in previous_attempts:
        if not isinstance(raw, dict):
            continue
        lift = raw.get("lift")
        number = raw.get("attempt_number")
        if lift in {"squat", "bench", "deadlift"} and number in {1, 2, 3}:
            item = copy.deepcopy(raw)
            item["attempt_id"] = str(item.get("attempt_id") or _attempt_id(master_id, lift, number))
            by_id[item["attempt_id"]] = item
            by_position[(lift, number)] = item["attempt_id"]

    attempts = incoming.get("attempts")
    if attempts is not None and not isinstance(attempts, list):
        raise ValueError("post_meet_report.attempts must be an array")
    seen_positions: set[tuple[str, int]] = set()
    for raw in attempts or []:
        if not isinstance(raw, dict):
            raise ValueError("post_meet_report.attempts entries must be objects")
        lift = raw.get("lift")
        number = raw.get("attempt_number")
        if lift not in {"squat", "bench", "deadlift"} or number not in {1, 2, 3}:
            raise ValueError("attempt lift and attempt_number are invalid")
        position = (lift, number)
        if position in seen_positions:
            raise ValueError("duplicate attempt identity")
        seen_positions.add(position)
        existing_id = by_position.get(position)
        supplied_id = str(raw["attempt_id"]) if raw.get("attempt_id") else None
        if existing_id and supplied_id and supplied_id != existing_id:
            raise ValueError("attempt identity is immutable")
        attempt_id = existing_id or supplied_id or _attempt_id(master_id, lift, number)
        prior = by_id.get(attempt_id)
        if prior and (prior.get("lift") != lift or prior.get("attempt_number") != number):
            raise ValueError("attempt identity is immutable")
        item = {**(prior or {}), **copy.deepcopy(raw), "attempt_id": attempt_id}
        by_id[attempt_id] = item
        by_position[position] = attempt_id

    report = {**copy.deepcopy(previous), **copy.deepcopy(incoming)}
    if attempts is not None or previous_attempts:
        report["attempts"] = list(by_id.values())
    return report


def list_competitions(args: dict) -> list[dict]:
    pk = args.get("pk") or HEALTH_PROGRAM_PK
    country = (args.get("country") or "").strip().lower() or None
    state = (args.get("state") or "").strip().lower() or None

    table = _get_table()
    items: list[dict] = []
    last_key = None
    while True:
        query_kwargs = {
            "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with("COMP#"),
        }
        if last_key:
            query_kwargs["ExclusiveStartKey"] = last_key
        response = table.query(**query_kwargs)
        for raw in response.get("Items", []) or []:
            comp = _from_item(raw) or {}
            comp.pop("pk", None)
            comp.pop("sk", None)
            comp["revision"] = int(comp.get("revision", 0))
            comp["units"] = comp.get("units") if comp.get("units") in {"kg", "lb"} else "kg"
            if country and (comp.get("venue_country") or "").strip().lower() != country:
                continue
            if state and (comp.get("venue_state") or "").strip().lower() != state:
                continue
            items.append(comp)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    active = active_block_id_for(pk)
    target = args.get("block_id") or active
    items = [comp for comp in items if _is_directory_entry(comp) or in_block(comp, target, active)]
    items.sort(key=lambda c: c.get("start_date") or "")
    return items


def _is_directory_entry(comp: dict) -> bool:
    return (comp.get("user_status") or comp.get("status") or "available") == "available"


def update_user_competition(args: dict, operation: str = "update") -> dict:
    pk = args.get("pk") or HEALTH_PROGRAM_PK
    master_id = args.get("master_id")
    if not master_id:
        raise ValueError("master_id is required")
    patch = args.get("patch")
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    expected_revision, idempotency_key = _mutation_envelope(args)
    unknown = set(patch) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"competition fields are not editable: {', '.join(sorted(unknown))}")
    if "units" in patch and patch["units"] not in {"kg", "lb"}:
        raise ValueError("competition.units must be kg or lb")

    table = _get_table()
    sk = f"COMP#{master_id}"
    key = {"pk": pk, "sk": sk}
    marker_sk = f"COMP_MUTATION#{master_id}#{idempotency_key}"
    payload_hash = _payload_hash(operation, master_id, patch)
    marker = table.get_item(Key={"pk": pk, "sk": marker_sk}, ConsistentRead=True).get("Item")
    if marker:
        if marker.get("payload_hash") != payload_hash:
            raise ValueError("idempotency key was used with a different payload")
        result = _from_item(marker.get("result")) or {}
        _invalidate_analysis_cache(pk)
        return result

    current_raw = table.get_item(Key=key, ConsistentRead=True).get("Item")
    if not current_raw:
        raise ValueError(f"Competition not found: {master_id}")
    current = _from_item(current_raw) or {}
    current_revision = int(current.get("revision", 0))
    current["units"] = current.get("units") if current.get("units") in {"kg", "lb"} else "kg"
    if current_revision != expected_revision:
        raise CompetitionConflictError(expected_revision, current_revision, current)

    applied = copy.deepcopy(patch)
    if not current.get("block_id") and not _is_directory_entry({**current, **applied}):
        applied["block_id"] = active_block_id_for(pk)
    entry_date = participation_date({**current, **applied})
    if entry_date and current.get("entry_date") != entry_date:
        applied["entry_date"] = entry_date
    removed = ["entry_date"] if not entry_date and current.get("entry_date") else []
    if "post_meet_report" in applied:
        if applied["post_meet_report"] is None and isinstance(current.get("post_meet_report"), dict) and current["post_meet_report"].get("attempts"):
            applied["post_meet_report"] = copy.deepcopy(current["post_meet_report"])
        elif applied["post_meet_report"] is not None:
            applied["post_meet_report"] = _normalise_report(master_id, applied["post_meet_report"], current.get("post_meet_report"))
    next_revision = current_revision + 1
    now = datetime.now(timezone.utc).isoformat()
    result = {**{key: value for key, value in current.items() if key not in removed}, **copy.deepcopy(applied), "revision": next_revision, "updated_at": now}
    result.pop("pk", None)
    result.pop("sk", None)
    marker_item = {
        "pk": pk,
        "sk": marker_sk,
        "entity_type": "competition_mutation",
        "operation": operation,
        "payload_hash": payload_hash,
        "result": _to_decimal(result),
        "revision": next_revision,
        "created_at": now,
    }
    table_name = getattr(table, "name", POWERLIFTING_USER_COMPETITIONS_TABLE)
    names = {"#pk": "pk", "#revision": "revision", "#updated_at": "updated_at"}
    values = {":expected": _to_decimal(expected_revision), ":next": _to_decimal(next_revision), ":updated": now}
    sets = ["#revision = :next", "#updated_at = :updated"]
    for field in removed:
        names[f"#{field}"] = field
    for field, value in applied.items():
        names[f"#{field}"] = field
        values[f":value_{field}"] = _to_decimal(value)
        sets.append(f"#{field} = :value_{field}")
    transactions = [
        {
            "Update": {
                "TableName": table_name,
                "Key": key,
                "UpdateExpression": "SET " + ", ".join(sets) + (" REMOVE " + ", ".join(f"#{field}" for field in removed) if removed else ""),
                "ConditionExpression": "attribute_exists(#pk) AND (attribute_not_exists(#revision) OR #revision = :expected)",
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        },
        {
            "Put": {
                "TableName": table_name,
                "Item": marker_item,
                "ConditionExpression": "attribute_not_exists(#pk)",
                "ExpressionAttributeNames": {"#pk": "pk"},
            }
        },
    ]
    try:
        table.meta.client.transact_write_items(TransactItems=transactions)
    except Exception as exc:
        replay = table.get_item(Key={"pk": pk, "sk": marker_sk}, ConsistentRead=True).get("Item")
        if replay and replay.get("payload_hash") == payload_hash:
            result = _from_item(replay.get("result")) or {}
            _invalidate_analysis_cache(pk)
            return result
        if _transaction_was_cancelled(exc):
            latest_raw = table.get_item(Key=key, ConsistentRead=True).get("Item")
            latest = _from_item(latest_raw) if latest_raw else None
            if latest is not None:
                raise CompetitionConflictError(expected_revision, int(latest.get("revision", 0)), latest) from exc
        raise
    _invalidate_analysis_cache(pk)
    return result


def complete_user_competition(args: dict) -> dict:
    pk = args.get("pk") or HEALTH_PROGRAM_PK
    master_id = args.get("master_id")
    if not master_id:
        raise ValueError("master_id is required")
    patch = {
        "user_status": "completed",
        "body_weight_kg": args.get("body_weight_kg"),
        "results": args.get("results"),
    }
    if args.get("post_meet_report") is not None:
        patch["post_meet_report"] = args["post_meet_report"]
    return update_user_competition({
        "pk": pk,
        "master_id": master_id,
        "patch": patch,
        "expected_revision": args.get("expected_revision"),
        "idempotency_key": args.get("idempotency_key"),
    }, operation="complete")


async def health_list_competitions(args: dict) -> dict:
    op = args.get("op")
    if not op:
        if args.get("master_id") and args.get("patch") is not None:
            op = "update"
        elif args.get("master_id") and args.get("results") is not None:
            op = "complete"
        else:
            op = "list"
    if op == "list":
        return {"competitions": list_competitions(args)}
    if op == "update":
        return update_user_competition(args)
    if op == "complete":
        return complete_user_competition(args)
    raise ValueError(f"unknown op: {op}")
