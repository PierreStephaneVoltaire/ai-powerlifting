import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

ROOT = Path(__file__).resolve().parents[1]
from services.lib.block_scope import BLOCK_SCOPED_RECORD_FIELDS, current_block_id
from services.lib.competition_entries import participation_date
from services.lib.program_store import ProgramStore

REGION = os.getenv("AWS_REGION", "ca-central-1")


def unstamped(record):
    return isinstance(record, dict) and not record.get("block_id") and (record.get("block") or "current") == "current"


def last_completed_block(program):
    completed = [block for block in (program.get("meta") or {}).get("blocks") or [] if block.get("status") == "completed"]
    if not completed:
        raise SystemExit("no completed block in meta.blocks; pass --block explicitly")
    return str(max(completed, key=lambda block: str(block.get("completed_at") or ""))["id"])


def query_prefix(table, pk, prefix):
    arguments = {"KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(prefix)}
    while True:
        response = table.query(**arguments)
        yield from response.get("Items", [])
        if not response.get("LastEvaluatedKey"):
            return
        arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def plan_program(program):
    return {field: sum(1 for record in program.get(field) or [] if unstamped(record)) for field in BLOCK_SCOPED_RECORD_FIELDS}


def stamp_program(program, target):
    for field in BLOCK_SCOPED_RECORD_FIELDS:
        for record in program.get(field) or []:
            if unstamped(record):
                record["block_id"] = target
                if "block" in record:
                    record["block"] = target
    return {"block_ids_backfilled_to": target}


def main():
    parser = argparse.ArgumentParser(description="Assign block_id to records written before block scoping.")
    parser.add_argument("--pk", required=True)
    parser.add_argument("--block", help="target block id; defaults to the most recently completed block")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--health-table", default=os.getenv("IF_HEALTH_TABLE_NAME", "if-health"))
    parser.add_argument("--budget-table", default=os.getenv("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"))
    parser.add_argument("--competitions-table", default=os.getenv("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"))
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    health = dynamodb.Table(args.health_table)
    budget = dynamodb.Table(args.budget_table)
    competitions = dynamodb.Table(args.competitions_table)

    store = ProgramStore(args.health_table, args.pk, region=REGION)
    program = asyncio.run(store.get_program())
    target = args.block or last_completed_block(program)
    active = current_block_id(program)
    if target == active:
        raise SystemExit(f"target block {target} is the active block; refusing")

    weight_logs = [item for item in query_prefix(health, args.pk, "weight_log#")]
    budget_items = [item for item in query_prefix(budget, args.pk, "ITEM#") if not item.get("block_id")]
    legacy_config = budget.get_item(Key={"pk": args.pk, "sk": "CONFIG#budget"}).get("Item")
    target_config = budget.get_item(Key={"pk": args.pk, "sk": f"CONFIG#budget#{target}"}).get("Item")
    participations = [item for item in query_prefix(competitions, args.pk, "COMP#") if participation_date(item)]
    entries = [item for item in participations if not item.get("block_id")]
    undated = [item for item in participations if item.get("entry_date") != participation_date(item)]

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "pk": args.pk,
        "target_block": target,
        "active_block": active,
        "program_records": plan_program(program),
        "weight_entries": {item["sk"]: sum(1 for entry in item.get("entries") or [] if unstamped(entry)) for item in weight_logs},
        "budget_items": len(budget_items),
        "budget_config": "copy CONFIG#budget -> CONFIG#budget#" + target if legacy_config and not target_config else "skip",
        "competition_entries": [item["sk"] for item in entries],
        "competition_entry_dates": {item["sk"]: participation_date(item) for item in undated},
        "pointer_current_block_id": active,
    }
    print(json.dumps(report, indent=2, default=str))
    if not args.apply:
        return

    revision = int((program.get("meta") or {}).get("revision", 0))
    asyncio.run(store.mutate_source("block_id_backfill", {"block": target}, revision, f"block-backfill-{uuid.uuid4()}", lambda current: stamp_program(current, target)))

    health.update_item(
        Key={"pk": args.pk, "sk": "program#current"},
        UpdateExpression="SET current_block_id = :active",
        ConditionExpression="attribute_exists(pk)",
        ExpressionAttributeValues={":active": active},
    )

    for item in weight_logs:
        entries_before = item.get("entries") or []
        if not any(unstamped(entry) for entry in entries_before):
            continue
        stamped = [{**entry, "block_id": target} if unstamped(entry) else entry for entry in entries_before]
        health.update_item(
            Key={"pk": args.pk, "sk": item["sk"]},
            UpdateExpression="SET entries = :entries, updated_at = :now",
            ConditionExpression="updated_at = :previous",
            ExpressionAttributeValues={":entries": stamped, ":now": datetime.now(timezone.utc).isoformat(), ":previous": item.get("updated_at")},
        )

    for item in budget_items:
        budget.update_item(
            Key={"pk": args.pk, "sk": item["sk"]},
            UpdateExpression="SET block_id = :block",
            ConditionExpression="attribute_not_exists(block_id)",
            ExpressionAttributeValues={":block": target},
        )

    if legacy_config and not target_config:
        budget.put_item(
            Item={**legacy_config, "sk": f"CONFIG#budget#{target}"},
            ConditionExpression="attribute_not_exists(sk)",
        )

    for item in entries:
        competitions.update_item(
            Key={"pk": args.pk, "sk": item["sk"]},
            UpdateExpression="SET block_id = :block",
            ConditionExpression="attribute_not_exists(block_id)",
            ExpressionAttributeValues={":block": target},
        )

    for item in undated:
        competitions.update_item(
            Key={"pk": args.pk, "sk": item["sk"]},
            UpdateExpression="SET entry_date = :date",
            ExpressionAttributeValues={":date": participation_date(item)},
        )

    print(json.dumps({"applied": True, "target_block": target}, indent=2))


if __name__ == "__main__":
    main()
