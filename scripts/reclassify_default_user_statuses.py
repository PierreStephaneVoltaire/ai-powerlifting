#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import boto3

DEFAULT_REGION = "ca-central-1"
USER_TABLE = "if-powerlifting-user-competitions"
LEGACY_SOURCE_NAME = "operator"
OLD_DEFAULT_STATUS = "optional"
NEW_DEFAULT_STATUS = "available"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scan_user_comps(client, target_pk: str):
    paginator = client.get_paginator("scan")
    for page in paginator.paginate(
        TableName=USER_TABLE,
        FilterExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": {"S": target_pk},
            ":prefix": {"S": "COMP#"},
        },
    ):
        for it in page.get("Items", []):
            yield it


def main() -> int:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--target-pk", action="append", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = boto3.client("dynamodb", region_name=args.region)
    now = _now_iso()
    total_scanned = 0
    total_updated = 0
    total_to_update = 0
    total_skipped_legacy = 0
    total_skipped_other = 0

    for pk in args.target_pk:
        scanned = 0
        updated = 0
        to_update = 0
        skipped_legacy = 0
        skipped_other = 0
        for it in _scan_user_comps(client, pk):
            scanned += 1
            source_name = it.get("source_name", {}).get("S")
            user_status = it.get("user_status", {}).get("S")
            if source_name == LEGACY_SOURCE_NAME:
                skipped_legacy += 1
                continue
            if user_status != OLD_DEFAULT_STATUS:
                skipped_other += 1
                continue
            to_update += 1
            sk = it["sk"]["S"]
            if args.dry_run:
                print(f"  [DRY] {pk} {sk}  optional -> available")
                continue
            client.update_item(
                TableName=USER_TABLE,
                Key={"pk": {"S": pk}, "sk": {"S": sk}},
                UpdateExpression="SET user_status = :new, updated_at = :now",
                ExpressionAttributeValues={
                    ":new": {"S": NEW_DEFAULT_STATUS},
                    ":now": {"S": now},
                },
            )
            updated += 1

        print(
            f"pk={pk}: scanned={scanned} updated={updated} "
            f"to_update={to_update} skipped_legacy={skipped_legacy} "
            f"skipped_other_status={skipped_other} dry_run={args.dry_run}"
        )
        total_scanned += scanned
        total_updated += updated
        total_to_update += to_update
        total_skipped_legacy += skipped_legacy
        total_skipped_other += skipped_other

    print(
        f"\nTOTAL: scanned={total_scanned} updated={total_updated} "
        f"to_update={total_to_update} skipped_legacy={total_skipped_legacy} "
        f"skipped_other_status={total_skipped_other} dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
