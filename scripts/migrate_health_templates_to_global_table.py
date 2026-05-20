#!/usr/bin/env python3
"""Migrate legacy health templates into the global template table.

Legacy templates lived in the health table under a user/program partition:
  pk=operator, sk=template#vNNN plus sk=template#current_list

The new library stores templates globally:
  pk=template_library, sk=template#...

This script copies template items, backfills published/author metadata, and
writes the new template#index item expected by TemplateStore.
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

LEGACY_INDEX_SK = "template#current_list"
NEW_INDEX_SK = "template#index"
TEMPLATE_SK_PREFIX = "template#"


def to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: to_dynamo(child) for key, child in value.items()}
    if isinstance(value, list):
        return [to_dynamo(child) for child in value]
    return value


def query_by_prefix(table: Any, pk: str, sk_prefix: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix),
    }
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def template_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        sk = str(item.get("sk") or "")
        if sk in {LEGACY_INDEX_SK, NEW_INDEX_SK}:
            continue
        if not isinstance(item.get("meta"), dict):
            continue
        result.append(item)
    return sorted(result, key=lambda row: str(row.get("sk") or ""))


def summary(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    return {
        "sk": item.get("sk"),
        "name": meta.get("name"),
        "source_filename": meta.get("source_filename"),
        "source_file_hash": meta.get("source_file_hash"),
        "estimated_weeks": meta.get("estimated_weeks"),
        "days_per_week": meta.get("days_per_week"),
        "archived": bool(meta.get("archived", False)),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "author": meta.get("author"),
        "author_pk": meta.get("author_pk"),
        "published": bool(meta.get("published", True)),
        "published_at": meta.get("published_at"),
        "import_job_id": meta.get("import_job_id"),
    }


def migrate_item(
    item: dict[str, Any],
    *,
    target_pk: str,
    source_table: str,
    source_pk: str,
    author_pk: str,
    author: str,
    now: str,
) -> dict[str, Any]:
    copied = copy.deepcopy(item)
    source_sk = str(copied.get("sk") or "")
    meta = copied.setdefault("meta", {})
    meta.setdefault("created_at", now)
    meta.setdefault("updated_at", now)
    meta.setdefault("archived", False)
    meta["published"] = True
    meta.setdefault("published_at", now)
    meta.setdefault("author_pk", author_pk)
    meta.setdefault("author", author)
    meta["migrated_from_table"] = source_table
    meta["migrated_from_pk"] = source_pk
    meta["migrated_from_sk"] = source_sk
    copied["pk"] = target_pk
    copied["sk"] = source_sk
    return copied


def put_items(table: Any, items: list[dict[str, Any]]) -> None:
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=to_dynamo(item))


def delete_items(table: Any, items: list[dict[str, Any]]) -> None:
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})


def main() -> int:
    parser = argparse.ArgumentParser(description="Move legacy health templates into the global template table.")
    parser.add_argument("--source-table", default=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"))
    parser.add_argument("--target-table", default=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ca-central-1"))
    parser.add_argument("--source-pk", default="operator")
    parser.add_argument("--target-pk", default=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"))
    parser.add_argument("--author-pk", default="operator")
    parser.add_argument("--author", default="operator")
    parser.add_argument("--replace", action="store_true", help="Replace existing target template-library items")
    parser.add_argument("--dry-run", action="store_true", help="Show planned writes without changing DynamoDB")
    parser.add_argument("--sample-keys", type=int, default=10)
    args = parser.parse_args()

    if args.source_table == args.target_table and args.source_pk == args.target_pk:
        print("ERROR: source and target resolve to the same table partition", file=sys.stderr)
        return 2

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    source_table = dynamodb.Table(args.source_table)
    target_table = dynamodb.Table(args.target_table)
    now = datetime.now(timezone.utc).isoformat()

    source_templates = template_items(query_by_prefix(source_table, args.source_pk, TEMPLATE_SK_PREFIX))
    migrated = [
        migrate_item(
            item,
            target_pk=args.target_pk,
            source_table=args.source_table,
            source_pk=args.source_pk,
            author_pk=args.author_pk,
            author=args.author,
            now=now,
        )
        for item in source_templates
    ]
    target_existing = query_by_prefix(target_table, args.target_pk, TEMPLATE_SK_PREFIX)
    index_item = {
        "pk": args.target_pk,
        "sk": NEW_INDEX_SK,
        "templates": [summary(item) for item in migrated],
        "updated_at": now,
    }

    print("[template-migration] Legacy health templates -> global template table")
    print(f"  Source table: {args.source_table}")
    print(f"  Target table: {args.target_table}")
    print(f"  Source PK:    {args.source_pk}")
    print(f"  Target PK:    {args.target_pk}")
    print(f"  Templates:    {len(migrated)}")
    print(f"  Existing target items: {len(target_existing)}")
    print(f"  Replace:      {args.replace}")
    print(f"  Dry run:      {args.dry_run}")
    for item in migrated[: args.sample_keys]:
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        print(f"    {item['sk']}  {meta.get('name') or '(unnamed)'}")

    if target_existing and not args.replace:
        print("Refusing to overwrite existing target templates. Re-run with --replace if intended.", file=sys.stderr)
        return 2

    if args.dry_run:
        print("Dry run only; no DynamoDB writes performed.")
        return 0

    if args.replace and target_existing:
        delete_items(target_table, target_existing)
        print(f"Deleted existing target template items: {len(target_existing)}")

    put_items(target_table, migrated + [index_item])
    print("Migration complete.")
    print(f"  Wrote template items: {len(migrated)}")
    print("  Wrote index item:     1")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        message = exc.response.get("Error", {}).get("Message", str(exc))
        print(f"AWS ERROR: {message}", file=sys.stderr)
        raise SystemExit(1)
