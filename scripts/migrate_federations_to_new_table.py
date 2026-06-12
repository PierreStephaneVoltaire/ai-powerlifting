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
SOURCE_SK = "federations#v1"
MASTER_TABLE = "if-powerlifting-master-federations"
USER_TABLE = "if-powerlifting-user-federations"
DEFAULT_TARGET_PK = "operator"


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


def _master_row(*, new_id: str, old: dict, now: str) -> dict:
    return {
        "pk": f"FED#{new_id}",
        "id": new_id,
        "name": old.get("name") or "Unnamed Federation",
        "abbreviation": old.get("abbreviation"),
        "region": old.get("region"),
        "website_url": old.get("website"),
        "status": "active" if old.get("status", "active") != "archived" else "archived",
        "source_slug": old.get("slug"),
        "legacy_federation_pk": old.get("id") or old.get("pk"),
        "created_at": now,
        "updated_at": now,
    }


def _user_row(*, target_pk: str, master: dict, now: str) -> dict:
    return {
        "pk": target_pk,
        "sk": f"FED#{master['id']}",
        "master_id": master["id"],
        "name": master["name"],
        "abbreviation": master["abbreviation"],
        "region": master["region"],
        "website_url": master["website_url"],
        "user_status": "active",
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }


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


def _scan_existing_slugs(ddb) -> set[str]:
    out: set[str] = set()
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=MASTER_TABLE, ProjectionExpression="source_slug"):
        for it in page.get("Items", []):
            slug = it.get("source_slug", {}).get("S")
            if slug:
                out.add(slug)
    return out


def migrate(args: argparse.Namespace) -> int:
    ddb = boto3.client("dynamodb", region_name=args.region)
    if args.verbose:
        print(f"Region:      {args.region}")
        print(f"Source:      {SOURCE_TABLE} pk={SOURCE_PK} sk={SOURCE_SK}")
        print(f"Target pk:   {args.target_pk}")
        print(f"Dry run:     {args.dry_run}")

    now = _now_iso()
    existing_slugs = set() if args.dry_run else _scan_existing_slugs(ddb)
    if args.verbose:
        print(f"Existing fed source_slugs: {len(existing_slugs)}")

    resp = ddb.get_item(TableName=SOURCE_TABLE, Key={"pk": {"S": SOURCE_PK}, "sk": {"S": SOURCE_SK}})
    item = resp.get("Item")
    if not item:
        print(f"[ERROR] no federations found at pk={SOURCE_PK} sk={SOURCE_SK}")
        return 1

    payload = _ddb_to_python(item)
    federations = payload.get("federations") or []
    if args.verbose:
        print(f"Found {len(federations)} legacy federations")

    created = 0
    skipped_dup_slug = 0
    for idx, old in enumerate(federations):
        slug = (old.get("slug") or "").strip() or None
        if slug and slug in existing_slugs:
            if args.verbose:
                print(f"  [{idx}] Skipping (slug already in master): {old.get('name')!r}")
            skipped_dup_slug += 1
            continue
        if slug:
            existing_slugs.add(slug)

        new_id = _make_id()
        master = _master_row(new_id=new_id, old=old, now=now)
        user = _user_row(target_pk=args.target_pk, master=master, now=now)

        if args.verbose:
            print(f"  [{idx}] {master['name']!r}  abbr={master['abbreviation']!r}  slug={slug!r}")
            print(f"      new master id={new_id}")

        _put(ddb, MASTER_TABLE, master, dry_run=args.dry_run)
        _put(ddb, USER_TABLE, user, dry_run=args.dry_run)
        created += 1

    print()
    print("=" * 60)
    print(f"Records read:        {len(federations)}")
    print(f"Created:             {created}")
    print(f"Skipped (dup slug):  {skipped_dup_slug}")
    print(f"Dry run:             {args.dry_run}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--target-pk", default=DEFAULT_TARGET_PK)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    return migrate(args)


if __name__ == "__main__":
    sys.exit(main())
