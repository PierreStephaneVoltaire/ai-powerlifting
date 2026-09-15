from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


TEMPLATE_PREFIX = "template#"
KNOWN_MARKER = "known-ownership-v1"


def pages(table: Any, pk: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    request = {"KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(TEMPLATE_PREFIX)}
    while True:
        response = table.query(**request)
        items.extend(response.get("Items", []))
        if not response.get("LastEvaluatedKey"):
            return items
        request["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def exact_person_mapping(user_items: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    ambiguous: set[str] = set()
    for item in user_items:
        person = str(item.get("pk") or "").strip()
        athlete = str(item.get("mapped_pk") or "").strip()
        if not person or not athlete or person.startswith("Identity#"):
            continue
        if athlete in ambiguous:
            continue
        if athlete in mapping and mapping[athlete] != person:
            mapping.pop(athlete)
            ambiguous.add(athlete)
            continue
        mapping[athlete] = person
    return mapping


def scan_user_records(user_table: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    request: dict[str, Any] = {}
    while True:
        response = user_table.scan(**request)
        items.extend(response.get("Items", []))
        if not response.get("LastEvaluatedKey"):
            return items
        request["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def load_mapping(user_table: Any, operator_person: str, operator_athlete: str) -> dict[str, str]:
    mapping = exact_person_mapping(scan_user_records(user_table))
    if mapping.get(operator_athlete) != operator_person:
        mapping.pop(operator_athlete, None)
    return mapping


def validate_supplied_mapping(supplied: dict[str, str], user_items: list[dict[str, Any]], authoritative: dict[str, str]) -> None:
    person_keys = {
        str(item.get("pk"))
        for item in user_items
        if item.get("pk") and not str(item.get("pk")).startswith("Identity#")
    }
    for legacy, target in supplied.items():
        if target not in person_keys:
            raise ValueError(f"mapping target Person {target!r} does not exist")
        if authoritative.get(legacy) != target:
            raise ValueError(f"mapping {legacy!r}->{target!r} does not match an unambiguous if-user mapping")


def template_update(item: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    legacy = str(meta.get("legacy_author_pk") or meta.get("author_pk") or item.get("author_pk") or "").strip()
    if not legacy:
        return None, "missing"
    person = mapping.get(legacy)
    if person is None:
        current = str(meta.get("author_person_pk") or "").strip()
        if current and meta.get(KNOWN_MARKER) == current and current in set(mapping.values()):
            return None, "unchanged"
        return None, "unknown"
    current = str(meta.get("author_person_pk") or "").strip()
    if current and current != person:
        return None, "ambiguous"
    if current == person and meta.get(KNOWN_MARKER) == person:
        return None, "unchanged"
    updated = copy.deepcopy(item)
    updated_meta = updated.setdefault("meta", {})
    updated_meta["author_person_pk"] = person
    updated_meta["legacy_author_pk"] = legacy
    updated_meta["author_pk"] = person
    updated_meta[KNOWN_MARKER] = person
    return updated, "updated"


def key(item: dict[str, Any]) -> dict[str, Any]:
    return {"pk": item["pk"], "sk": item["sk"]}


def apply_updates(table: Any, updates: list[dict[str, Any]]) -> tuple[int, int]:
    written = skipped = 0
    for item in updates:
        source_meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        desired_person = str(source_meta.get("author_person_pk") or "")
        old_author = str(source_meta.get("legacy_author_pk") or "")
        revision = source_meta.get("revision")
        names = {"meta": "meta", "author": "author_pk", "person": "author_person_pk", "legacy": "legacy_author_pk", "marker": KNOWN_MARKER}
        values = {":person": desired_person, ":legacy": old_author, ":marker_value": desired_person, ":old_author": old_author}
        conditions = ["attribute_exists(pk)", "#meta.#author = :old_author"]
        if revision is not None:
            names["revision"] = "revision"
            values[":revision"] = revision
            conditions.append("#meta.#revision = :revision")
        try:
            table.update_item(
                Key=key(item),
                UpdateExpression="SET #meta.#author = :person, #meta.#person = :person, #meta.#legacy = :legacy, #meta.#marker = :marker_value",
                ConditionExpression=" AND ".join(conditions),
                ExpressionAttributeNames={f"#{name}": value for name, value in names.items()},
                ExpressionAttributeValues=values,
            )
            written += 1
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            existing = table.get_item(Key=key(item), ConsistentRead=True).get("Item") or {}
            existing_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}
            if existing_meta.get("author_person_pk") == desired_person and existing_meta.get(KNOWN_MARKER) == desired_person:
                skipped += 1
                continue
            raise RuntimeError(f"Refusing to overwrite changed template {key(item)}") from exc
    return written, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Add known Person ownership to legacy template metadata.")
    parser.add_argument("--table", default=os.getenv("IF_TEMPLATES_TABLE_NAME", "if-health-templates"))
    parser.add_argument("--user-table", default=os.getenv("IF_USER_TABLE", "if-user"))
    parser.add_argument("--library-pk", default=os.getenv("IF_TEMPLATES_LIBRARY_PK", "template_library"))
    parser.add_argument("--operator-person", default=os.getenv("IF_OPERATOR_PERSON_PK", "sir_simpalot"))
    parser.add_argument("--operator-athlete", default=os.getenv("HEALTH_PROGRAM_PK", "operator"))
    parser.add_argument("--mapping-file", help="JSON object mapping legacy Athlete keys to Person keys")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sample-keys", type=int, default=10)
    args = parser.parse_args()
    if args.apply and args.dry_run:
        print("ERROR: --apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 2
    dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1"))
    template_table = dynamodb.Table(args.table)
    user_table = dynamodb.Table(args.user_table)
    user_items = scan_user_records(user_table)
    mapping = exact_person_mapping(user_items)
    if mapping.get(args.operator_athlete) != args.operator_person:
        mapping.pop(args.operator_athlete, None)
    if args.mapping_file:
        with open(args.mapping_file, encoding="utf-8") as handle:
            supplied = json.load(handle)
        if not isinstance(supplied, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in supplied.items()):
            raise ValueError("mapping file must contain an object of string keys and values")
        validate_supplied_mapping(supplied, user_items, mapping)
    updates: list[dict[str, Any]] = []
    counts = {"updated": 0, "unknown": 0, "ambiguous": 0, "missing": 0, "unchanged": 0}
    for item in pages(template_table, args.library_pk):
        updated, status = template_update(item, mapping)
        counts[status] += 1
        if updated:
            updates.append(updated)
    print("[known-ownership] legacy template author -> Person")
    print(f"  templates: {sum(counts.values())}")
    print(f"  planned updates: {len(updates)}")
    print(f"  unknown or ambiguous authors skipped: {counts['unknown'] + counts['ambiguous']}")
    print(f"  mode: {'apply' if args.apply else 'dry-run'}")
    for item in updates[: args.sample_keys]:
        print(f"    {item['pk']} {item['sk']}")
    if not args.apply:
        print("Dry run only; no DynamoDB writes performed.")
        return 0
    written, skipped = apply_updates(template_table, updates)
    print(f"Applied additive ownership metadata: wrote {written}, already migrated {skipped}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        message = exc.response.get("Error", {}).get("Message", str(exc))
        print(f"AWS ERROR: {message}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
