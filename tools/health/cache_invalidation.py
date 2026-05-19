"""DynamoDB analysis-cache invalidation helpers for health writes."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterable

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


def _table(table_name: str | None = None, region: str | None = None):
    return boto3.resource(
        "dynamodb",
        region_name=region or os.environ.get("AWS_REGION", "ca-central-1"),
    ).Table(table_name or os.environ.get("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"))


def _analysis_pk(pk: str) -> str:
    return pk if pk.startswith("analysis#") else f"analysis#{pk}"


def _delete_keys(table, keys: list[dict]) -> None:
    for i in range(0, len(keys), 25):
        batch = keys[i:i + 25]
        if not batch:
            continue
        with table.batch_writer() as writer:
            for key in batch:
                writer.delete_item(Key=key)


def invalidate_analysis_caches(
    pk: str,
    table_name: str | None = None,
    region: str | None = None,
    prefixes: Iterable[str] | None = None,
) -> None:
    """Delete generated current-analysis cache records for a user.

    This intentionally removes cached analysis and markdown content, but it does
    not set the coach markdown dirty marker. The dirty marker is reserved for
    session completion so coach runs do not refresh after every health write.
    """
    table = _table(table_name, region)
    cache_pk = _analysis_pk(pk)
    target_prefixes = tuple(prefixes or (
        "weekly_analysis#",
        "analysis_section#",
        "analysis_job#",
        "markdown_export#current",
    ))
    keys: list[dict] = []
    for prefix in target_prefixes:
        last_key = None
        while True:
            params = {
                "KeyConditionExpression": Key("pk").eq(cache_pk) & Key("sk").begins_with(prefix),
                "ProjectionExpression": "pk, sk",
            }
            if last_key:
                params["ExclusiveStartKey"] = last_key
            response = table.query(**params)
            keys.extend(
                {"pk": item["pk"], "sk": item["sk"]}
                for item in response.get("Items", [])
                if item.get("pk") and item.get("sk")
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
    if keys:
        _delete_keys(table, keys)
        logger.info("[AnalysisCache] invalidated %s records for %s", len(keys), cache_pk)


def mark_markdown_export_dirty(
    pk: str,
    table_name: str | None = None,
    region: str | None = None,
    reason: str = "session_completion",
) -> None:
    table = _table(table_name, region)
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        "pk": _analysis_pk(pk),
        "sk": "markdown_export_dirty#current",
        "reason": reason,
        "dirty_at": now,
        "updated_at": now,
        "expires_at": int(time.time()) + 7 * 86400,
    })


def clear_markdown_export_dirty(
    pk: str,
    table_name: str | None = None,
    region: str | None = None,
) -> None:
    table = _table(table_name, region)
    table.delete_item(Key={"pk": _analysis_pk(pk), "sk": "markdown_export_dirty#current"})
