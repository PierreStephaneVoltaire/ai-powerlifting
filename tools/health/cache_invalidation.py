"""DynamoDB cache invalidation helpers for health analysis outputs."""
from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


def _batch_delete(table: Any, keys: list[dict[str, str]]) -> None:
    if not keys:
        return
    with table.batch_writer() as batch:
        for key in keys:
            batch.delete_item(Key=key)


def _query_keys(table: Any, pk: str, sk_prefix: str | None = None) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(pk),
        "ProjectionExpression": "pk, sk",
    }
    if sk_prefix:
        query_kwargs["KeyConditionExpression"] = Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)

    while True:
        response = table.query(**query_kwargs)
        for item in response.get("Items", []):
            item_pk = item.get("pk")
            item_sk = item.get("sk")
            if isinstance(item_pk, str) and isinstance(item_sk, str):
                keys.append({"pk": item_pk, "sk": item_sk})
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        query_kwargs["ExclusiveStartKey"] = last_key

    return keys


def invalidate_analysis_caches(pk: str, health_table_name: str | None = None, region: str | None = None) -> None:
    """Delete cached powerlifting analysis outputs for one user partition.

    This intentionally does not recompute anything. The next analysis read will
    rebuild and persist a fresh cache object.
    """
    resolved_region = region or os.getenv("AWS_REGION", "ca-central-1")
    dynamodb = boto3.resource("dynamodb", region_name=resolved_region)

    analysis_table_name = os.getenv("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache")
    try:
        analysis_table = dynamodb.Table(analysis_table_name)
        _batch_delete(analysis_table, _query_keys(analysis_table, f"analysis#{pk}"))
    except Exception as exc:
        logger.warning("[AnalysisCache] Failed to invalidate weekly bundle cache for pk=%s: %s", pk, exc)

    resolved_health_table = health_table_name or os.getenv("IF_HEALTH_TABLE_NAME", "if-health")
    try:
        health_table = dynamodb.Table(resolved_health_table)
        keys = _query_keys(health_table, pk, "corr_report#")
        keys.extend(_query_keys(health_table, pk, "program_eval#"))
        _batch_delete(health_table, keys)
    except Exception as exc:
        logger.warning("[AnalysisCache] Failed to invalidate AI report caches for pk=%s: %s", pk, exc)
