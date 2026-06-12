#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

DEFAULT_REGION = "ca-central-1"
SOURCE_TABLE = "if-health"
SOURCE_PK = "operator"
SOURCE_SK = "program#v020"
DEST_TABLE = "if-powerlifting-goals"


def _unwrap(tagged: dict) -> Any:
    if not tagged:
        return None
    tag = next(iter(tagged))
    raw = tagged[tag]
    if tag in ("S", "B"):
        return raw
    if tag == "N":
        return Decimal(raw) if "." in raw else int(raw)
    if tag == "BOOL":
        return raw
    if tag == "NULL":
        return None
    if tag == "M":
        return {k: _unwrap(v) for k, v in raw.items()}
    if tag == "L":
        return [_unwrap(v) for v in raw]
    if tag == "SS":
        return list(raw)
    if tag == "NS":
        return [Decimal(x) for x in raw]
    return raw


def _ddb_to_python(item: dict) -> Any:
    if not item:
        return {}
    if set(item.keys()) <= {"S", "N", "M", "L", "B", "BOOL", "NULL", "SS", "NS"}:
        return _unwrap(item)
    return {k: _ddb_to_python(v) for k, v in item.items()}


def _floats_to_decimals(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    return obj


def _to_ddb(value: Any) -> dict:
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, Decimal)):
        return {"N": str(value)}
    if isinstance(value, float):
        return {"N": str(Decimal(str(value)))}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, list):
        return {"L": [_to_ddb(v) for v in value]}
    if isinstance(value, dict):
        return {"M": {k: _to_ddb(v) for k, v in value.items()}}
    return {"S": str(value)}


def _put(ddb, table: str, item: dict, *, dry_run: bool) -> None:
    payload = {k: _to_ddb(v) for k, v in _floats_to_decimals(item).items()}
    if dry_run:
        print(f"  [DRY] PutItem {table} sk={item.get('sk')} id={item.get('id')}")
        return
    ddb.put_item(TableName=table, Item=payload)


def migrate(args: argparse.Namespace) -> int:
    ddb = boto3.client("dynamodb", region_name=args.region)

    resp = ddb.get_item(TableName=SOURCE_TABLE, Key={"pk": {"S": SOURCE_PK}, "sk": {"S": SOURCE_SK}})
    item = resp.get("Item")
    if not item:
        print(f"[ERROR] no legacy program at {SOURCE_TABLE} pk={SOURCE_PK} sk={SOURCE_SK}")
        return 1
    program = _ddb_to_python(item)
    legacy_goals: list[dict] = program.get("goals") or []
    print(f"Legacy goals: {len(legacy_goals)}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for pk in args.target_pk:
        print(f"\n=== target_pk={pk} ===")
        for g in legacy_goals:
            gid = g.get("id") or str(uuid.uuid4())
            stored = {
                "pk": pk,
                "sk": f"GOAL#{gid}",
                "id": gid,
                "title": g.get("title") or "Untitled Goal",
                "goal_type": g.get("goal_type", "training_quality"),
                "priority": g.get("priority", "primary"),
                "strategy_mode": g.get("strategy_mode", "max_total"),
                "risk_tolerance": g.get("risk_tolerance", "medium"),
                "target_competition_dates": g.get("target_competition_dates") or [],
                "target_competition_date": g.get("target_competition_date"),
                "target_date": g.get("target_date"),
                "target_federation_id": g.get("target_federation_id"),
                "target_standard_ids": g.get("target_standard_ids") or [],
                "target_standard_id": g.get("target_standard_id"),
                "target_total_kg": g.get("target_total_kg"),
                "target_dots": g.get("target_dots"),
                "target_ipf_gl": g.get("target_ipf_gl"),
                "target_weight_class_kg": g.get("target_weight_class_kg"),
                "acceptable_weight_classes_kg": g.get("acceptable_weight_classes_kg") or [],
                "max_acceptable_bodyweight_loss_pct": g.get("max_acceptable_bodyweight_loss_pct"),
                "max_acceptable_water_cut_pct": g.get("max_acceptable_water_cut_pct"),
                "notes": g.get("notes") or "",
                "target_competition_ids": [],
                "created_at": now,
                "updated_at": now,
            }
            _put(ddb, DEST_TABLE, stored, dry_run=args.dry_run)
            if args.verbose:
                print(f"  + {g.get('title', 'Untitled')!r} (id={gid})")

    print()
    print("=" * 60)
    print(f"Records read:    {len(legacy_goals)}")
    print(f"Targets:         {args.target_pk}")
    print(f"Dry run:         {args.dry_run}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--target-pk", action="append", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    return migrate(args)


if __name__ == "__main__":
    sys.exit(main())
