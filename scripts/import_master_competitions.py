#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

DEFAULT_REGION = "ca-central-1"
MASTER_COMP_TABLE = "if-powerlifting-master-competitions"
USER_COMP_TABLE = "if-powerlifting-user-competitions"
MASTER_FED_TABLE = "if-powerlifting-master-federations"
USER_FED_TABLE = "if-powerlifting-user-federations"
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


VALID_TESTING = {"tested", "untested", "unknown"}
VALID_REGISTRATION = {"open", "closed", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low"}

REGISTRATION_ALIASES = {"not_open_yet": "unknown", "coming_soon": "unknown"}


def _norm_enum(value: Any, valid: set, aliases: dict | None = None) -> str:
    if value is None:
        return "unknown"
    v = str(value).strip().lower()
    if aliases and v in aliases:
        v = aliases[v]
    return v if v in valid else "unknown"


def _maybe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f != f or f == float("inf") or f == float("-inf") else f
    except (TypeError, ValueError):
        return None


def _scan_fed_source_slugs(ddb) -> dict[str, dict]:
    """Return {source_slug: master_fed_dict} for every master fed that has
    a non-null source_slug. Also returns every fed keyed by legacy_federation_pk
    in case the source data uses one of those IDs."""
    by_slug: dict[str, dict] = {}
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=MASTER_FED_TABLE):
        for it in page.get("Items", []):
            py = _ddb_to_python(it)
            slug = py.get("source_slug")
            if slug:
                by_slug[slug] = py
    return by_slug


def _new_master_fed(*, name: str, slug: str, website_url: str | None, now: str) -> dict:
    return {
        "pk": f"FED#{_make_id()}",
        "id": "",  # filled below
        "name": name or "Unnamed Federation",
        "abbreviation": None,
        "region": None,
        "website_url": website_url,
        "status": "active",
        "source_slug": slug,
        "created_at": now,
        "updated_at": now,
    }


def _new_user_fed(*, target_pk: str, master: dict, now: str) -> dict:
    return {
        "pk": target_pk,
        "sk": f"FED#{master['id']}",
        "master_id": master["id"],
        "name": master["name"],
        "abbreviation": master.get("abbreviation"),
        "region": master.get("region"),
        "website_url": master.get("website_url"),
        "user_status": "active",
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }


def _resolve_or_create_federation(
    ddb,
    *,
    fed_obj: dict,
    fed_slug_map: dict[str, dict],
    target_pk: str,
    now: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Returns a master fed dict. Reuses by source_slug, otherwise creates a new one."""
    slug = (fed_obj.get("slug") or "").strip()
    if slug and slug in fed_slug_map:
        return fed_slug_map[slug]

    new_id = _make_id()
    name = fed_obj.get("name") or "Unnamed Federation"
    website_url = fed_obj.get("websiteUrl")
    master = _new_master_fed(name=name, slug=slug, website_url=website_url, now=now)
    master["id"] = new_id
    master["pk"] = f"FED#{new_id}"
    user = _new_user_fed(target_pk=target_pk, master=master, now=now)

    if verbose:
        print(f"    + new master federation: {name!r} (slug={slug!r}) id={new_id}")
    _put(ddb, MASTER_FED_TABLE, master, dry_run=dry_run)
    _put(ddb, USER_FED_TABLE, user, dry_run=dry_run)

    fed_slug_map[slug] = master
    return master


def _build_master_comp(*, rec: dict, fed_id: str | None, fed_label: str | None, fed_slug: str | None, fed_website: str | None, now: str) -> dict:
    new_id = _make_id()
    venue = rec.get("venue") or {}
    return {
        "pk": f"COMP#{new_id}",
        "id": new_id,
        "name": rec.get("name") or "Unnamed Competition",
        "start_date": rec.get("startDate"),
        "end_date": rec.get("endDate"),
        "federation_id": fed_id,
        "federation_label": fed_label,
        "federation_slug": fed_slug,
        "federation_website_url": fed_website,
        "venue_name": (venue.get("name") or None) or None,
        "venue_address": venue.get("addressLine1"),
        "venue_city": venue.get("city"),
        "venue_state": venue.get("state"),
        "venue_country": venue.get("country"),
        "venue_postal_code": venue.get("postalCode"),
        "venue_latitude": _maybe_float(venue.get("latitude")),
        "venue_longitude": _maybe_float(venue.get("longitude")),
        "venue_coordinate_quality": venue.get("coordinateQuality"),
        "website_url": None,
        "testing_status": _norm_enum(rec.get("testingStatus"), VALID_TESTING),
        "registration_status": _norm_enum(
            rec.get("registrationStatus"), VALID_REGISTRATION, REGISTRATION_ALIASES
        ),
        "registration_url": rec.get("registrationUrl"),
        "registration_end_date": None,
        "source_url": rec.get("sourceUrl"),
        "source_name": rec.get("sourceName") or "imported",
        "last_verified_at": rec.get("lastVerifiedAt"),
        "confidence_status": _norm_enum(rec.get("confidenceStatus"), VALID_CONFIDENCE),
        "slug": rec.get("slug"),
        "cancelled": False,
        "is_sample_data": bool(rec.get("isSampleData", False)),
        "created_at": now,
        "updated_at": now,
    }


def _build_user_comp(*, target_pk: str, master: dict, now: str) -> dict:
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
        "user_status": "available",
        "weight_class_kg": None,
        "body_weight_kg": None,
        "targets": None,
        "results": None,
        "post_meet_report": None,
        "hotel_required": False,
        "counts_toward_federation_ids": [],
        "between_comp_plan": None,
        "comp_day_protocol": None,
        "decision_date": None,
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
        print(f"    [DRY] PutItem {table} pk={item.get('pk')} sk={item.get('sk','-')}")
        return
    ddb.put_item(TableName=table, Item=payload)


def _scan_existing_slugs(ddb) -> set[str]:
    out: set[str] = set()
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=MASTER_COMP_TABLE, ProjectionExpression="slug"):
        for it in page.get("Items", []):
            slug = it.get("slug", {}).get("S")
            if slug:
                out.add(slug)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Import master comps")
    parser.add_argument("files", nargs="+", help="One or more JSON files to import")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--target-pk", default=DEFAULT_TARGET_PK)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    ddb = boto3.client("dynamodb", region_name=args.region)
    if args.verbose:
        print(f"Region:      {args.region}")
        print(f"Target pk:   {args.target_pk}")
        print(f"Dry run:     {args.dry_run}")
        print(f"Files:       {args.files}")

    now = _now_iso()
    existing_slugs = set() if args.dry_run else _scan_existing_slugs(ddb)
    if args.verbose:
        print(f"Existing slugs in master comps: {len(existing_slugs)}")
    fed_slug_map = _scan_fed_source_slugs(ddb) if not args.dry_run else {}
    if args.verbose:
        print(f"Existing fed source_slugs: {len(fed_slug_map)}")

    total_files = 0
    total_records = 0
    created = 0
    skipped_dup_slug = 0
    skipped_no_data = 0
    new_feds_created = 0

    for path in args.files:
        if not os.path.exists(path):
            print(f"[WARN] file not found: {path}")
            continue
        total_files += 1
        try:
            with open(path) as f:
                doc = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"[WARN] invalid JSON in {path}: {exc}")
            continue

        results = doc.get("results") if isinstance(doc, dict) else None
        if not isinstance(results, list):
            print(f"[WARN] {path} has no 'results' array. Skipping.")
            continue

        print(f"\n=== {path} ===")
        print(f"  {len(results)} records (total={doc.get('total','?')})")

        for idx, rec in enumerate(results):
            total_records += 1
            slug = (rec.get("slug") or "").strip()
            if not slug:
                print(f"  [{idx}] Skipping (no slug): name={rec.get('name')!r}")
                skipped_no_data += 1
                continue
            if slug in existing_slugs:
                if args.verbose:
                    print(f"  [{idx}] Skipping (slug already in master): {rec.get('name')!r} {rec.get('startDate')}")
                skipped_dup_slug += 1
                continue
            existing_slugs.add(slug)  # protect against intra-batch dupes

            fed_obj = rec.get("federation") or {}
            fed_slug = (fed_obj.get("slug") or "").strip()
            was_new_fed = bool(fed_slug) and fed_slug not in fed_slug_map
            fed_master = _resolve_or_create_federation(
                ddb,
                fed_obj=fed_obj,
                fed_slug_map=fed_slug_map,
                target_pk=args.target_pk,
                now=now,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
            if was_new_fed:
                new_feds_created += 1

            master = _build_master_comp(
                rec=rec,
                fed_id=fed_master.get("id"),
                fed_label=fed_master.get("name"),
                fed_slug=fed_obj.get("slug"),
                fed_website=fed_obj.get("websiteUrl"),
                now=now,
            )
            user = _build_user_comp(target_pk=args.target_pk, master=master, now=now)

            if args.verbose:
                v = rec.get("venue") or {}
                loc = f'{v.get("city","")}, {v.get("state","")} {v.get("country","")}'.strip(", ")
                print(f"  [{idx}] {rec.get('name')!r}")
                print(f"      slug={slug}")
                print(f"      dates={rec.get('startDate')} -> {rec.get('endDate')}")
                print(f"      location={loc}")
                print(f"      fed={fed_master.get('name')!r} ({fed_obj.get('slug')})")
                print(f"      testing={rec.get('testingStatus')}  reg={rec.get('registrationStatus')}")
                print(f"      new master id={master['id']}")

            _put(ddb, MASTER_COMP_TABLE, master, dry_run=args.dry_run)
            _put(ddb, USER_COMP_TABLE, user, dry_run=args.dry_run)
            created += 1

    print()
    print("=" * 60)
    print(f"Files processed:        {total_files}")
    print(f"Records read:           {total_records}")
    print(f"Created:                {created}")
    print(f"Skipped (duplicate slug): {skipped_dup_slug}")
    print(f"Skipped (no slug):      {skipped_no_data}")
    print(f"New feds created:       {new_feds_created}")
    print(f"Dry run:                {args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
