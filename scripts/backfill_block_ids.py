import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.lib.block_scope import BLOCK_SCOPED_RECORD_FIELDS, current_block_id, record_block, record_date
from services.lib.competition_entries import participation_date
from services.lib.program_store import ProgramStore

REGION = os.getenv("AWS_REGION", "ca-central-1")


def assigned_block(record, field, program):
    if not isinstance(record, dict):
        return None
    return record_block(record, field, program)


def needs_correction(record, field, program):
    if not isinstance(record, dict):
        return False
    target = assigned_block(record, field, program)
    stamped = record.get("block_id") or record.get("block")
    return bool(target) and stamped != target


def query_prefix(table, pk, prefix):
    arguments = {"KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(prefix)}
    while True:
        response = table.query(**arguments)
        yield from response.get("Items", [])
        if not response.get("LastEvaluatedKey"):
            return
        arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def plan_program(program):
    return {field: sum(1 for record in program.get(field) or [] if needs_correction(record, field, program)) for field in BLOCK_SCOPED_RECORD_FIELDS}


def record_identifier(record, field, index):
    for key in ("id", "sk", "name", "date", "phase", "phase_name"):
        if record.get(key) not in (None, ""):
            return str(record[key])
    return f"{field}[{index}]"


def report_records(records, field, program):
    return [
        {
            "identifier": record_identifier(record, field, index),
            "date": record_date(record) or participation_date(record) if field == "competitions" else record_date(record),
            "target_block": record_block(record, field, program),
        }
        for index, record in enumerate(records or [])
        if needs_correction(record, field, program)
    ]


def program_report(program):
    report = {field: report_records(program.get(field), field, program) for field in BLOCK_SCOPED_RECORD_FIELDS}
    meta = program.get("meta") or {}
    report["meta.block_notes"] = report_records(meta.get("block_notes"), "meta.block_notes", program)
    report["block_notes"] = report_records(program.get("block_notes"), "block_notes", program)
    return report


def stamp_program(program):
    for field in BLOCK_SCOPED_RECORD_FIELDS:
        for record in program.get(field) or []:
            if needs_correction(record, field, program):
                assigned = assigned_block(record, field, program)
                record["block_id"] = assigned
                if "block" in record:
                    record["block"] = assigned
    meta = program.get("meta") or {}
    for record in meta.get("block_notes") or []:
        if needs_correction(record, "meta.block_notes", program):
            record["block_id"] = assigned_block(record, "meta.block_notes", program)
            if "block" in record:
                record["block"] = record["block_id"]
    for record in program.get("block_notes") or []:
        if needs_correction(record, "block_notes", program):
            record["block_id"] = assigned_block(record, "block_notes", program)
            if "block" in record:
                record["block"] = record["block_id"]
    return program


def main():
    parser = argparse.ArgumentParser(description="Preview block_id assignments for records written before block scoping.")
    parser.add_argument("--pk", required=True)
    parser.add_argument("--health-table", default=os.getenv("IF_HEALTH_TABLE_NAME", "if-health"))
    parser.add_argument("--budget-table", default=os.getenv("POWERLIFTING_BUDGET_TABLE", "if-powerlifting-budget"))
    parser.add_argument("--competitions-table", default=os.getenv("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    health = dynamodb.Table(args.health_table)
    budget = dynamodb.Table(args.budget_table)
    competitions = dynamodb.Table(args.competitions_table)
    store = ProgramStore(args.health_table, args.pk, region=REGION)
    program = asyncio.run(store.get_program())
    weight_logs = list(query_prefix(health, args.pk, "weight_log#"))
    budget_items = list(query_prefix(budget, args.pk, "ITEM#"))
    competition_entries = [item for item in query_prefix(competitions, args.pk, "COMP#") if participation_date(item)]

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "pk": args.pk,
        "active_block": current_block_id(program),
        "program_records": program_report(program),
        "weight_entries": {
            item["sk"]: report_records(item.get("entries"), "weight_log", program)
            for item in weight_logs
        },
        "budget_items": report_records(budget_items, "budget", program),
        "competition_entries": report_records(competition_entries, "competitions", program),
    }
    if args.apply:
        updated_program = stamp_program(program)
        _, _, program_sk, _, revision = store._source_snapshot_sync()
        asyncio.run(store.mutate_source(
            "backfill_block_ids",
            {"fields": list(BLOCK_SCOPED_RECORD_FIELDS)},
            revision,
            f"backfill-block-ids-{uuid.uuid4().hex}",
            lambda current: current.update(updated_program) or {"updated": True},
        ))
        for item in weight_logs:
            entries = item.get("entries") or []
            changed = False
            for record in entries:
                if needs_correction(record, "weight_log", program):
                    record["block_id"] = assigned_block(record, "weight_log", program)
                    changed = True
            if changed:
                health.put_item(Item=ProgramStore._floats_to_decimals({**item, "entries": entries}))
        for item in budget_items:
            if needs_correction(item, "budget", program):
                target = assigned_block(item, "budget", program)
                budget.put_item(Item=ProgramStore._floats_to_decimals({**item, "block_id": target}))
        for item in competition_entries:
            if needs_correction(item, "competitions", program):
                target = assigned_block(item, "competitions", program)
                competitions.put_item(Item=ProgramStore._floats_to_decimals({**item, "block_id": target}))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
