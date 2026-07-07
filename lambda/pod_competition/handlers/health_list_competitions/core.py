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
import os
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.types import TypeDeserializer

from .config import (
    AWS_REGION,
    HEALTH_PROGRAM_PK,
    POWERLIFTING_USER_COMPETITIONS_TABLE,
)

logger = logging.getLogger(__name__)

_deserializer = TypeDeserializer()
_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(
            POWERLIFTING_USER_COMPETITIONS_TABLE
        )
    return _table


def _from_item(item: Optional[dict]) -> Optional[dict]:
    if not item:
        return None
    return {k: _deserializer.deserialize(v) if hasattr(v, "items") else v for k, v in item.items()}


def _to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    return value


def list_competitions(args: dict) -> list[dict]:
    pk = args.get("pk") or HEALTH_PROGRAM_PK
    country = (args.get("country") or "").strip().lower() or None
    state = (args.get("state") or "").strip().lower() or None

    table = _get_table()
    items: list[dict] = []
    last_key = None
    while True:
        scan_kwargs = {
            "FilterExpression": "begins_with(pk, :pfx) AND begins_with(sk, :sk_pfx)",
            "ExpressionAttributeValues": {":pfx": pk, ":sk_pfx": "COMP#"},
        }
        if last_key:
            scan_kwargs["ExclusiveStartKey"] = last_key
        response = table.scan(**scan_kwargs)
        for raw in response.get("Items", []) or []:
            comp = _from_item(raw) or {}
            comp.pop("pk", None)
            comp.pop("sk", None)
            if country and (comp.get("venue_country") or "").strip().lower() != country:
                continue
            if state and (comp.get("venue_state") or "").strip().lower() != state:
                continue
            items.append(comp)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    items.sort(key=lambda c: c.get("start_date") or "")
    return items


def update_user_competition(args: dict) -> dict:
    pk = args.get("pk") or HEALTH_PROGRAM_PK
    master_id = args.get("master_id")
    if not master_id:
        raise ValueError("master_id is required")
    patch = args.get("patch") or {}
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")
    if not patch:
        return {"master_id": master_id, "updated_fields": []}

    table = _get_table()
    sk = f"COMP#{master_id}"
    update_kwargs = {
        "Key": {"pk": pk, "sk": sk},
        "UpdateExpression": "SET " + ", ".join(f"#{k} = :{k}" for k in patch.keys()),
        "ExpressionAttributeNames": {f"#{k}": k for k in patch.keys()},
        "ExpressionAttributeValues": {f":{k}": _to_decimal(v) for k, v in patch.items()},
        "ReturnValues": "ALL_NEW",
    }
    response = table.update_item(**update_kwargs)
    comp = _from_item(response.get("Attributes")) or {}
    comp.pop("pk", None)
    comp.pop("sk", None)
    return comp


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
    return update_user_competition({"pk": pk, "master_id": master_id, "patch": patch})


async def health_list_competitions(args: dict) -> dict:
    op = args.get("op") or "list"
    if op == "list":
        return {"competitions": list_competitions(args)}
    if op == "update":
        return update_user_competition(args)
    if op == "complete":
        return complete_user_competition(args)
    raise ValueError(f"unknown op: {op}")
