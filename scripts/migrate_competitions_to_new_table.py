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
SOURCE_VERSION = "v020"
MASTER_TABLE = "if-powerlifting-master-competitions"
USER_TABLE = "if-powerlifting-user-competitions"
MASTER_FED_TABLE = "if-powerlifting-master-federations"
SOURCE_SK = f"program#{SOURCE_VERSION}"


def _floats_to_decimals(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    return obj


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_id() -> str:
    return str(uuid.uuid4())


def _unwrap_value(tagged: dict) -> Any:
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
        return _ddb_to_python(raw)
    if tag == "L":
        return [_ddb_to_python(v) for v in raw]
    if tag == "SS":
        return list(raw)
    if tag == "NS":
        return [Decimal(x) for x in raw]
    return raw


def _ddb_to_python(item: dict) -> Any:
    if not item:
        return {}
    if set(item.keys()) <= {"S", "N", "M", "L", "B", "BOOL", "NULL", "SS", "NS"}:
        return _unwrap_value(item)
    return {k: _ddb_to_python(v) for k, v in item.items()}


def _build_fed_id_map(ddb) -> dict[str, str]:
    out: dict[str, str] = {}
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=MASTER_FED_TABLE):
        for it in page.get("Items", []):
            py = _ddb_to_python(it)
            legacy = py.get("legacy_federation_pk")
            new_id = py.get("id")
            if legacy and new_id:
                out[legacy] = new_id
    return out


def _master_row(*, new_id: str, old: dict, fed_id_map: dict[str, str], now: str) -> dict:
    legacy_fed_id = old.get("federation_id") or None
    new_fed_id = fed_id_map.get(legacy_fed_id, legacy_fed_id) if legacy_fed_id else None

    return {
        "pk": f"COMP#{new_id}",
        "id": new_id,
        "name": old.get("name") or "Unnamed Competition",
        "start_date": old.get("date"),
        "end_date": None,
        "federation_id": new_fed_id,
        "federation_label": old.get("federation") or None,
        "federation_slug": None,
        "federation_website_url": None,
        "venue_name": None,
        "venue_address": None,
        "venue_city": None,
        "venue_state": None,
        "venue_country": None,
        "venue_postal_code": None,
        "venue_latitude": None,
        "venue_longitude": None,
        "venue_coordinate_quality": None,
        "website_url": None,
        "testing_status": "unknown",
        "registration_status": "unknown",
        "registration_url": None,
        "registration_end_date": None,
        "source_url": None,
        "source_name": "operator",
        "last_verified_at": None,
        "confidence_status": None,
        "slug": None,
        "cancelled": False,
        "is_sample_data": False,
        "legacy_competition_date": old.get("date"),
        "created_at": now,
        "updated_at": now,
    }


VALID_USER_STATUS = {"available", "confirmed", "optional", "completed", "skipped"}


def _user_row(*, target_pk: str, master: dict, old: dict, now: str) -> dict:
    user_status = old.get("status") or "available"
    if user_status not in VALID_USER_STATUS:
        user_status = "available"
    weight_class = old.get("weight_class_kg")
    if weight_class is not None:
        try:
            weight_class = float(weight_class)
        except (TypeError, ValueError):
            weight_class = None

    return {
        "pk": target_pk,
        "sk": f"COMP#{master['id']}",
        "master_id": master["id"],
        "name": master["name"],
        "start_date": master["start_date"],
        "end_date": master["end_date"],
        "federation_id": master["federation_id"],
        "federation_label": master["federation_label"],
        "federation_slug": master["federation_slug"],
        "federation_website_url": master["federation_website_url"],
        "venue_name": master["venue_name"],
        "venue_address": master["venue_address"],
        "venue_city": master["venue_city"],
        "venue_state": master["venue_state"],
        "venue_country": master["venue_country"],
        "venue_postal_code": master["venue_postal_code"],
        "venue_latitude": master["venue_latitude"],
        "venue_longitude": master["venue_longitude"],
        "venue_coordinate_quality": master["venue_coordinate_quality"],
        "website_url": master["website_url"],
        "testing_status": master["testing_status"],
        "registration_status": master["registration_status"],
        "registration_url": master["registration_url"],
        "registration_end_date": master["registration_end_date"],
        "source_url": master["source_url"],
        "source_name": master["source_name"],
        "last_verified_at": master["last_verified_at"],
        "confidence_status": master["confidence_status"],
        "cancelled": master["cancelled"],
        "user_status": user_status,
        "weight_class_kg": weight_class,
        "body_weight_kg": _maybe_float(old.get("body_weight_kg")),
        "targets": old.get("targets"),
        "results": old.get("results"),
        "post_meet_report": old.get("post_meet_report"),
        "hotel_required": bool(old.get("hotel_required", False)),
        "counts_toward_federation_ids": old.get("counts_toward_federation_ids") or [],
        "between_comp_plan": old.get("between_comp_plan"),
        "comp_day_protocol": old.get("comp_day_protocol"),
        "decision_date": old.get("decision_date"),
        "attempt_selection": old.get("attempt_selection"),
        "attempt_strategy_mode": old.get("attempt_strategy_mode"),
        "qualifying_standard_id": old.get("qualifying_standard_id"),
        "qualifying_total_kg": _maybe_float(old.get("qualifying_total_kg")),
        "projected_at_t_minus_1w": old.get("projected_at_t_minus_1w"),
        "projection_snapshot_date": old.get("projection_snapshot_date"),
        "notes": old.get("notes") or "",
        "created_at": now,
        "updated_at": now,
    }


def _maybe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_ddb_value(obj: Any) -> Any:
    if obj is None:
        return {"NULL": True}
    if isinstance(obj, bool):
        return {"BOOL": obj}
    if isinstance(obj, (int, Decimal)):
        return {"N": str(obj)}
    if isinstance(obj, float):
        return {"N": str(Decimal(str(obj)))}
    if isinstance(obj, str):
        return {"S": obj}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return {"L": [_to_ddb_value(v) for v in obj]}
    if isinstance(obj, dict):
        return {"M": {k: _to_ddb_value(v) for k, v in obj.items()}}
    return {"S": str(obj)}


def _to_ddb_attrs(item: dict) -> dict:
    return {k: _to_ddb_value(v) for k, v in _floats_to_decimals(item).items()}


def _put(ddb, table: str, item: dict, *, dry_run: bool) -> None:
    payload = _to_ddb_attrs(item)
    if dry_run:
        print(f"  [DRY] PutItem {table} pk={item.get('pk')} sk={item.get('sk','-')}")
        return
    ddb.put_item(TableName=table, Item=payload)


def _resolve_version_sk(ddb, pk: str, version: str) -> str:
    if version == "current":
        resp = ddb.get_item(
            TableName=SOURCE_TABLE,
            Key={"pk": {"S": pk}, "sk": {"S": "program#current"}},
        )
        item = resp.get("Item")
        if not item:
            return "program#v001"
        return item.get("ref_sk", {}).get("S", "program#v001")
    return f"program#{version}"


def migrate(args: argparse.Namespace) -> int:
    ddb = boto3.client("dynamodb", region_name=args.region)
    if args.verbose:
        print(f"Region:      {args.region}")
        print(f"Source:      {SOURCE_TABLE} pk={SOURCE_PK} sk={SOURCE_SK}")
        print(f"Target pk:   {args.target_pk}")
        print(f"Dry run:     {args.dry_run}")

    now = _now_iso()
    fed_id_map = _build_fed_id_map(ddb) if not args.dry_run else {}
    if args.verbose:
        print(f"Federation id mappings: {len(fed_id_map)}")

    sk = _resolve_version_sk(ddb, SOURCE_PK, args.version)
    if args.verbose:
        print(f"Resolved source sk: {sk}")

    resp = ddb.get_item(TableName=SOURCE_TABLE, Key={"pk": {"S": SOURCE_PK}, "sk": {"S": sk}})
    item = resp.get("Item")
    if not item:
        print(f"[ERROR] no program found at pk={SOURCE_PK} sk={sk}")
        return 1

    program = _ddb_to_python(item)
    competitions = program.get("competitions") or []
    if args.verbose:
        print(f"Found {len(competitions)} legacy competitions")

    created = 0
    for idx, old in enumerate(competitions):
        new_id = _make_id()
        master = _master_row(new_id=new_id, old=old, fed_id_map=fed_id_map, now=now)
        user = _user_row(target_pk=args.target_pk, master=master, old=old, now=now)

        if args.verbose:
            print(f"  [{idx}] {master['name']!r} {master['start_date']}  fed={master['federation_label']!r}")
            print(f"      user_status={user['user_status']!r}  weight_class_kg={user['weight_class_kg']}")
            print(f"      new master id={new_id}")

        _put(ddb, MASTER_TABLE, master, dry_run=args.dry_run)
        _put(ddb, USER_TABLE, user, dry_run=args.dry_run)
        created += 1

    print()
    print("=" * 60)
    print(f"Records read:        {len(competitions)}")
    print(f"Created:             {created}")
    print(f"Dry run:             {args.dry_run}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--pk", default=os.environ.get("IF_OPERATOR_PK", "operator"))
    parser.add_argument("--target-pk", default=os.environ.get("IF_OPERATOR_PK", "operator"))
    parser.add_argument("--version", default=SOURCE_VERSION, help="program version (e.g. v020)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    return migrate(args)


if __name__ == "__main__":
    sys.exit(main())
