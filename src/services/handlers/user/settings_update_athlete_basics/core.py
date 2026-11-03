from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import date, datetime, timezone

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from botocore.exceptions import ClientError
from services.lib.program_store import ProgramStore

from ..settings_get.core import _get_table, _normalize_settings, _sanitize_username, _sanitize_decimals

SEX_VALUES = ("male", "female")
MIN_BODYWEIGHT_KG = 30.0
MAX_BODYWEIGHT_KG = 300.0
MIN_LIFT_KG = 20.0
MAX_LIFT_KG = 600.0


def _to_positive_float(value, *, lo: float, hi: float, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a finite number")
    if v < lo or v > hi:
        raise ValueError(f"{name} must be between {lo} and {hi} kg")
    return round(v, 2)


def _validate_athlete_basics(input_data: dict) -> dict:
    if not isinstance(input_data, dict):
        raise ValueError("input must be an object")
    sex = input_data.get("sex")
    if sex not in SEX_VALUES:
        raise ValueError("sex must be 'male' or 'female'")
    country = input_data.get("country")
    if not isinstance(country, str) or not country.strip():
        raise ValueError("country is required")
    country_v = country.strip().upper()
    if len(country_v) > 8:
        raise ValueError("country must be a short code (<= 8 chars)")
    region = input_data.get("region")
    if region is not None and not isinstance(region, str):
        raise ValueError("region must be a string")
    region_v = str(region).strip()[:64] if isinstance(region, str) and str(region).strip() else None
    bodyweight = _to_positive_float(
        input_data.get("bodyweight_kg"),
        lo=MIN_BODYWEIGHT_KG,
        hi=MAX_BODYWEIGHT_KG,
        name="bodyweight_kg",
    )
    maxes = input_data.get("training_maxes")
    if not isinstance(maxes, dict):
        raise ValueError("training_maxes is required")
    squat = _to_positive_float(maxes.get("squat_kg"), lo=MIN_LIFT_KG, hi=MAX_LIFT_KG, name="squat_kg")
    bench = _to_positive_float(maxes.get("bench_kg"), lo=MIN_LIFT_KG, hi=MAX_LIFT_KG, name="bench_kg")
    deadlift = _to_positive_float(maxes.get("deadlift_kg"), lo=MIN_LIFT_KG, hi=MAX_LIFT_KG, name="deadlift_kg")
    maxes_date = input_data.get("maxes_date") or date.today().isoformat()
    if not isinstance(maxes_date, str):
        raise ValueError('Maxes date must be YYYY-MM-DD')
    if date.fromisoformat(maxes_date) > date.today():
        raise ValueError("Maxes date cannot be in the future")
    estimated = input_data.get("training_maxes_estimated", {})
    if not isinstance(estimated, dict) or any(key not in ("squat", "bench", "deadlift") or not isinstance(value, bool) for key, value in estimated.items()):
        raise ValueError("Estimated maxes must identify squat, bench, or deadlift with booleans")
    return {
        "maxes_date": maxes_date,
        "training_maxes_estimated": {lift: estimated.get(lift, False) for lift in ("squat", "bench", "deadlift")},
        "sex": sex,
        "country": country_v,
        "region": region_v,
        "bodyweight_kg": bodyweight,
        "training_maxes": {
            "squat_kg": squat,
            "bench_kg": bench,
            "deadlift_kg": deadlift,
        },
    }


async def settings_update_athlete_basics(args: dict) -> dict:
    table = _get_table()
    username = _sanitize_username(args["username"])
    validated = _validate_athlete_basics(args.get("input") or args)

    def save():
        existing = table.get_item(Key={"pk": username}, ConsistentRead=True).get("Item")
        if not existing or "athlete" not in existing.get("roles", []):
            raise ValueError("The Athlete role is required")
        athlete = existing.get("mapped_pk") or existing["pk"]
        health = dynamodb_resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1")).Table(os.getenv("IF_HEALTH_TABLE_NAME", "if-health"))
        history_key = {"pk": athlete, "sk": "max_history#current"}
        history = health.get_item(Key=history_key, ConsistentRead=True).get("Item") or {}
        entry = {"date": validated["maxes_date"], **validated["training_maxes"], "estimated": validated["training_maxes_estimated"], "source": "athlete_basics"}
        entry_id = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
        entry.update(id=entry_id, total_kg=sum(validated["training_maxes"].values()))
        now = datetime.now(timezone.utc).isoformat()
        changes = {**validated, "ranking_country": validated["country"], "ranking_region": validated["region"], "athlete_basics_complete": True, "updated_at": now}
        names = {f"#f{i}": key for i, key in enumerate(changes)}
        values = {f":v{i}": value for i, value in enumerate(changes.values())}
        names["#updated"] = "updated_at"
        condition = "attribute_not_exists(#updated)"
        if "updated_at" in existing:
            condition = "#updated = :previous"
            values[":previous"] = existing["updated_at"]
        update = {"TableName": table.name, "Key": {"pk": existing["pk"]}, "UpdateExpression": "SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(changes))), "ConditionExpression": condition, "ExpressionAttributeNames": names, "ExpressionAttributeValues": ProgramStore._floats_to_decimals(values)}
        transaction = [{"Update": update}]
        if entry_id not in history.get("basics_entry_ids", set()):
            transaction.append({"Update": {"TableName": health.name, "Key": history_key,
                "UpdateExpression": "SET entries = list_append(if_not_exists(entries, :empty), :entry), #version = :version, updated_at = :now ADD basics_entry_ids :ids",
                "ConditionExpression": "attribute_not_exists(basics_entry_ids) OR NOT contains(basics_entry_ids, :id)",
                "ExpressionAttributeNames": {"#version": "version"},
                "ExpressionAttributeValues": ProgramStore._floats_to_decimals({":empty": [], ":entry": [entry], ":version": "current", ":now": now, ":ids": {entry_id}, ":id": entry_id})}})
        try:
            table.meta.client.transact_write_items(TransactItems=transaction)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            from services.dispatch import OperationError
            raise OperationError(409, "conflict", "Your profile changed. Reload it before saving these basics.") from exc
        return _normalize_settings(_sanitize_decimals({**existing, **changes}))

    return await asyncio.to_thread(save)
