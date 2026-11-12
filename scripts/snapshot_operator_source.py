#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
OPL_BUCKET = "powerlifting-data-2b0f699b"
OPL_PREFIX = "datasets/openpowerlifting-"

HEALTH = "if-health"
SESSIONS = "if-sessions"
GOALS = "if-powerlifting-goals"
COMPETITIONS = "if-powerlifting-user-competitions"


class Ledger:
    def __init__(self):
        self.units = {}
        self.items = {}

    def add(self, table, response, items):
        capacity = (response.get("ConsumedCapacity") or {}).get("CapacityUnits", 0)
        self.units[table] = self.units.get(table, 0) + capacity
        self.items[table] = self.items.get(table, 0) + items


def pk_value(athlete):
    return {"S": athlete}


def get_item(client, ledger, table, athlete, sk):
    response = client.get_item(
        TableName=table,
        Key={"pk": pk_value(athlete), "sk": {"S": sk}},
        ReturnConsumedCapacity="TOTAL",
    )
    item = response.get("Item")
    ledger.add(table, response, 1 if item else 0)
    return item


def query_all(client, ledger, table, **kwargs):
    items = []
    while True:
        response = client.query(TableName=table, ReturnConsumedCapacity="TOTAL", **kwargs)
        page = response.get("Items", [])
        ledger.add(table, response, len(page))
        items.extend(page)
        last = response.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def prefix_query(client, ledger, table, athlete, prefix):
    return query_all(
        client,
        ledger,
        table,
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": pk_value(athlete), ":prefix": {"S": prefix}},
    )


def write(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n")


def snapshot_source(client, athlete, out, ledger):
    pointer = get_item(client, ledger, HEALTH, athlete, "program#current")
    if not pointer or "ref_sk" not in pointer:
        raise SystemExit(f"No program#current pointer for {athlete}")
    ref_sk = pointer["ref_sk"]["S"]
    program = get_item(client, ledger, HEALTH, athlete, ref_sk)
    if not program:
        raise SystemExit(f"Pointed program {ref_sk} not found for {athlete}")
    glossary = get_item(client, ledger, HEALTH, athlete, "glossary#v1")
    weight_logs = prefix_query(client, ledger, HEALTH, athlete, "weight_log#")
    health = [item for item in [pointer, program, glossary] if item] + weight_logs
    sessions = prefix_query(client, ledger, SESSIONS, athlete, f"session#{ref_sk}#")
    goals = prefix_query(client, ledger, GOALS, athlete, "GOAL#")
    competitions = query_all(
        client,
        ledger,
        COMPETITIONS,
        IndexName="entries-by-date",
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": pk_value(athlete)},
    )
    source = out / "source"
    write(source / f"{HEALTH}.json", health)
    write(source / f"{SESSIONS}.json", sessions)
    write(source / f"{GOALS}.json", goals)
    write(source / f"{COMPETITIONS}.json", competitions)
    return {HEALTH: len(health), SESSIONS: len(sessions), GOALS: len(goals), COMPETITIONS: len(competitions)}


def download_opl(region):
    s3 = boto3.client("s3", region_name=region)
    objects = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=OPL_BUCKET, Prefix=OPL_PREFIX):
        objects.extend(obj for obj in page.get("Contents", []) if obj["Key"].endswith(".csv"))
    if not objects:
        print("no OPL dataset found")
        return
    newest = max(objects, key=lambda obj: (obj["LastModified"], obj["Key"]))
    target = FIXTURES / "opl"
    target.mkdir(parents=True, exist_ok=True)
    destination = target / Path(newest["Key"]).name
    if destination.exists() and destination.stat().st_size == newest["Size"]:
        print(f"opl dataset already present: {destination}")
        return
    s3.download_file(OPL_BUCKET, newest["Key"], str(destination))
    print(f"downloaded {destination}")


def main():
    parser = argparse.ArgumentParser(description="Read-only snapshot of the operator's source items into fixtures/operator/source.")
    parser.add_argument("--athlete", default="operator")
    parser.add_argument("--region", default=None)
    parser.add_argument("--skip-opl", action="store_true")
    args = parser.parse_args()

    session = boto3.session.Session(region_name=args.region)
    region = session.region_name or "ca-central-1"
    client = session.client("dynamodb", region_name=region)
    ledger = Ledger()
    counts = snapshot_source(client, args.athlete, FIXTURES / "operator", ledger)
    for table, count in counts.items():
        print(f"{table}: {count} items written, {ledger.items[table]} read, {ledger.units[table]} read capacity units")
    if not args.skip_opl:
        download_opl(region)


if __name__ == "__main__":
    sys.exit(main())
