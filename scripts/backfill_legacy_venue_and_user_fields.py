#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from decimal import Decimal
from typing import Any

import boto3

DEFAULT_REGION = "ca-central-1"
SOURCE_TABLE = "if-health"
SOURCE_PK = "operator"
SOURCE_SK = "program#v020"
MASTER_TABLE = "if-powerlifting-master-competitions"
USER_TABLE = "if-powerlifting-user-competitions"


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


def _python_to_ddb(value: Any) -> dict:
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
        return {"L": [_python_to_ddb(v) for v in value]}
    if isinstance(value, dict):
        return {"M": {k: _python_to_ddb(v) for k, v in value.items()}}
    return {"S": str(value)}


PROVINCE_ABBREV_TO_NAME = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "NT": "Northwest Territories", "NU": "Nunavut",
    "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}
PROVINCE_NAMES = sorted(set(PROVINCE_ABBREV_TO_NAME.values()), key=len, reverse=True)
ABBREV_RE = r"\b(" + "|".join(PROVINCE_ABBREV_TO_NAME.keys()) + r")\b"
NAME_RE = r"\b(" + "|".join(re.escape(n) for n in PROVINCE_NAMES) + r")\b"
COUNTRY_KEYWORDS = [r"\bcanada\b", r",\s*ca\b", r"\bca\s*\d", r"\bontario\b", r"\bquebec\b", r"\bbritish columbia\b", r"\balberta\b"]


def _parse_venue_from_location(location: str) -> dict[str, str | None]:
    if not location:
        return {"venue_country": None, "venue_state": None, "venue_city": None, "venue_address": None, "venue_postal_code": None}
    cleaned = location.replace("—", ",").replace("–", ",").replace(";", ",")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")

    country = "CA" if re.search("|".join(COUNTRY_KEYWORDS), cleaned, re.IGNORECASE) else None
    if not country and re.search(r"\b(usa|united states|tx|ca|fl|ny|oh|va|mo|pa)\b", cleaned, re.IGNORECASE) and not re.search(ABBREV_RE, cleaned, re.IGNORECASE):
        country = "US"

    state = None
    m = re.search(ABBREV_RE, cleaned)
    if m:
        state = m.group(1)
    else:
        m = re.search(NAME_RE, cleaned, re.IGNORECASE)
        if m:
            full = next((v for k, v in PROVINCE_ABBREV_TO_NAME.items() if v.lower() == m.group(1).lower()), None)
            state = full

    city = None
    head = cleaned.split(",")[0].strip()
    head = re.sub(r"\d+.*$", "", head).strip()
    head = re.sub(r"\b(legion|club|centre|center|barbell|gym|training)\b.*$", "", head, flags=re.IGNORECASE).strip()
    if head and len(head) >= 3:
        city = head

    postal = None
    m = re.search(r"\b([A-Z]\d[A-Z]\s?\d[A-Z]\d)\b", cleaned)
    if m:
        postal = m.group(1)

    address_parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    address = ", ".join(address_parts[:3]) if address_parts else None

    return {
        "venue_country": country,
        "venue_state": state,
        "venue_city": city,
        "venue_address": address,
        "venue_postal_code": postal,
    }


def _scan_user_comps(client, target_pk: str):
    paginator = client.get_paginator("scan")
    for page in paginator.paginate(
        TableName=USER_TABLE,
        FilterExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": {"S": target_pk}, ":prefix": {"S": "COMP#"}},
    ):
        for it in page.get("Items", []):
            yield it


def _scan_master_for_legacy(ddb):
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=MASTER_TABLE):
        for it in page.get("Items", []):
            if it.get("source_name", {}).get("S") == "operator":
                yield it


def backfill(args: argparse.Namespace) -> int:
    ddb = boto3.client("dynamodb", region_name=args.region)

    resp = ddb.get_item(TableName=SOURCE_TABLE, Key={"pk": {"S": SOURCE_PK}, "sk": {"S": SOURCE_SK}})
    item = resp.get("Item")
    if not item:
        print(f"[ERROR] no legacy program at {SOURCE_TABLE} pk={SOURCE_PK} sk={SOURCE_SK}")
        return 1
    legacy_comps = _ddb_to_python(item).get("competitions") or []
    print(f"Legacy comps: {len(legacy_comps)}")

    by_legacy_key: dict[str, dict] = {}
    for old in legacy_comps:
        key = f"{old.get('date')}|{old.get('name')}"
        by_legacy_key[key] = old
    print(f"Legacy index keys: {sorted(by_legacy_key.keys())[:3]} ...")

    total_updated_user = 0
    total_updated_master = 0
    total_skipped = 0
    total_no_match = 0

    for pk in args.target_pk:
        print(f"\n=== target_pk={pk} ===")
        for urow in _scan_user_comps(ddb, pk):
            if urow.get("source_name", {}).get("S") != "operator":
                continue
            name = urow.get("name", {}).get("S", "")
            date = urow.get("start_date", {}).get("S", "")
            key = f"{date}|{name}"
            old = by_legacy_key.get(key)
            if not old:
                total_no_match += 1
                continue

            venue = _parse_venue_from_location(old.get("location") or "")
            user_updates: dict[str, Any] = {}
            for vfield, vval in venue.items():
                if vval and not urow.get(vfield, {}).get("S"):
                    user_updates[vfield] = vval

            for field in ("attempt_strategy_mode", "qualifying_standard_id", "qualifying_total_kg",
                          "projected_at_t_minus_1w", "projection_snapshot_date", "attempt_selection"):
                if field in old and old.get(field) is not None and not urow.get(field):
                    user_updates[field] = old.get(field)

            if not user_updates:
                total_skipped += 1
                continue

            update_expr_parts = []
            expr_names = {}
            expr_values = {}
            for i, (k, v) in enumerate(user_updates.items()):
                ph_name = f"#f{i}"
                ph_val = f":v{i}"
                update_expr_parts.append(f"{ph_name} = {ph_val}")
                expr_names[ph_name] = k
                expr_values[ph_val] = _floats_to_decimals(v)
            update_expr_parts.append("#u = :u")
            expr_names["#u"] = "updated_at"
            expr_values[":u"] = {"S": "2026-06-12T04:00:00Z"}

            if args.dry_run:
                if args.verbose:
                    print(f"  [DRY] user {name[:40]:40s} {date} -> {sorted(user_updates.keys())}")
                total_updated_user += 1
                continue

            try:
                ddb.update_item(
                    TableName=USER_TABLE,
                    Key={"pk": {"S": pk}, "sk": urow["sk"]},
                    UpdateExpression="SET " + ", ".join(update_expr_parts),
                    ExpressionAttributeNames=expr_names,
                    ExpressionAttributeValues={k: _python_to_ddb(v) for k, v in expr_values.items()},
                )
                total_updated_user += 1
                if args.verbose:
                    print(f"  + user {name[:40]:40s} {date} -> {sorted(user_updates.keys())}")
            except Exception as exc:
                print(f"  [ERR] user update failed for {name}: {exc}")

            master_id = urow.get("master_id", {}).get("S")
            if master_id:
                try:
                    master_update_parts = []
                    master_names = {}
                    master_values = {}
                    for i, (k, v) in enumerate(venue.items()):
                        if v is not None:
                            ph_name = f"#m{i}"
                            ph_val = f":mv{i}"
                            master_update_parts.append(f"{ph_name} = {ph_val}")
                            master_names[ph_name] = k
                            master_values[ph_val] = _floats_to_decimals(v)
                    if master_update_parts:
                        if args.dry_run:
                            total_updated_master += 1
                            if args.verbose:
                                print(f"  [DRY] master {name[:40]:40s} {date} -> {sorted([k for k, v in venue.items() if v is not None])}")
                            continue
                        ddb.update_item(
                            TableName=MASTER_TABLE,
                            Key={"pk": {"S": f"COMP#{master_id}"}},
                            UpdateExpression="SET " + ", ".join(master_update_parts),
                            ExpressionAttributeNames=master_names,
                            ExpressionAttributeValues={k: _python_to_ddb(v) for k, v in master_values.items()},
                        )
                        total_updated_master += 1
                except Exception as exc:
                    print(f"  [ERR] master update failed for {name}: {exc}")

    print()
    print("=" * 60)
    print(f"User rows updated:  {total_updated_user}")
    print(f"Master rows updated: {total_updated_master}")
    print(f"Skipped (no updates needed): {total_skipped}")
    print(f"No match in legacy: {total_no_match}")
    print(f"Dry run: {args.dry_run}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--target-pk", action="append", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    return backfill(args)


if __name__ == "__main__":
    sys.exit(main())
