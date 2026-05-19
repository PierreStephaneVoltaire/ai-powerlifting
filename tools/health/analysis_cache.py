"""Python-side client for the if-powerlifting-analysis-cache DynamoDB table.

Reads back the per-window plain JSON items written by the TypeScript backend
and/or by the Python regenerate_analysis tool.

Schema (new, as of cache schema v5):
  pk  = analysis#{user_pk}
  sk  = weekly_analysis#{window_key}          → per-window weekly analysis (current block, 7-day TTL)
  sk  = markdown_export#current                → markdown export (current block, 7-day TTL)
  sk  = markdown_export#{block_key}            → markdown export for a past block (no TTL)
  sk  = block_analysis#v1#{block_key}          → block analysis bundle (handled by blockAnalytics.ts)
  ...

Legacy items (schema v4 and earlier) stored gzip+base64 in payload_gzip_b64.
_hydrate_item() handles both formats for backward compat.
"""
from __future__ import annotations

import gzip
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger(__name__)

CURRENT_BLOCK_TTL_DAYS = 7


class AnalysisCacheStore:
    def __init__(
        self,
        table_name: Optional[str] = None,
        pk: str = "operator",
        region: str = "ca-central-1",
    ) -> None:
        self._table_name = table_name or os.environ.get(
            "ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"
        )
        self._pk = f"analysis#{pk}"
        self._region = region
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(
                self._table_name
            )
        return self._table

    # ── Low-level helpers ─────────────────────────────────────────────────────

    def _hydrate_item(self, item: dict) -> Optional[Any]:
        """Decode a DynamoDB item's payload — plain JSON (new) or gzip+b64 (legacy)."""
        # New format: plain JSON string in `payload`
        payload_str = item.get("payload", "")

        # Sharded new format
        if not payload_str:
            shard_count = int(item.get("shard_count", 0))
            sk = item.get("sk", "")
            if shard_count > 0:
                parts = []
                for i in range(shard_count):
                    shard_sk = f"{sk}#shard#{i:03d}"
                    p_resp = self.table.get_item(Key={"pk": self._pk, "sk": shard_sk})
                    parts.append(p_resp.get("Item", {}).get("payload", ""))
                payload_str = "".join(parts)

        # Legacy gzip+base64 (schema v4 and earlier)
        if not payload_str:
            legacy_b64 = item.get("payload_gzip_b64", "")
            if legacy_b64:
                try:
                    payload_str = gzip.decompress(
                        base64.b64decode(legacy_b64)
                    ).decode("utf-8")
                except Exception as exc:
                    logger.error("[AnalysisCacheStore] Legacy gzip decode failed: %s", exc)
                    return None

            # Legacy sharded gzip
            if not payload_str:
                shard_count = int(item.get("shard_count", 0))
                sk = item.get("sk", "")
                if shard_count > 0:
                    parts = []
                    for i in range(shard_count):
                        part_sk = f"{sk}#part#{i:03d}"
                        p_resp = self.table.get_item(Key={"pk": self._pk, "sk": part_sk})
                        parts.append(p_resp.get("Item", {}).get("payload_gzip_b64", ""))
                    legacy_joined = "".join(parts)
                    if legacy_joined:
                        try:
                            payload_str = gzip.decompress(
                                base64.b64decode(legacy_joined)
                            ).decode("utf-8")
                        except Exception as exc:
                            logger.error("[AnalysisCacheStore] Legacy sharded gzip decode failed: %s", exc)
                            return None

        if not payload_str:
            return None

        try:
            return json.loads(payload_str)
        except Exception as exc:
            logger.error("[AnalysisCacheStore] JSON parse failed: %s", exc)
            return None

    def _put_json_item(
        self,
        sk: str,
        data: Any,
        ttl_days: Optional[int] = None,
        extra_fields: Optional[dict] = None,
    ) -> None:
        """Write plain JSON to the analysis-cache table."""
        payload_str = json.dumps(data, default=str)
        item: dict = {
            "pk": self._pk,
            "sk": sk,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload_str,
        }
        if ttl_days is not None:
            item["expires_at"] = int(time.time()) + ttl_days * 86400
        if extra_fields:
            item.update(extra_fields)
        self.table.put_item(Item=item)

    # ── Block analysis (used by agents to inspect block cache state) ──────────

    def get_cached_block_analysis(self, block_key: str) -> Optional[dict]:
        """Find the latest version of this block analysis in DynamoDB."""
        try:
            resp = self.table.query(
                KeyConditionExpression=Key("pk").eq(self._pk)
                & Key("sk").begins_with("block_analysis#"),
                FilterExpression=Attr("sk").contains(f"#{block_key}"),
            )
            items = resp.get("Items", [])
            if not items:
                return None

            items.sort(
                key=lambda x: (
                    int(x.get("schema_version", 0)),
                    x.get("generated_at", ""),
                ),
                reverse=True,
            )
            return self._hydrate_item(items[0])
        except Exception as exc:
            logger.error("[AnalysisCacheStore] get_cached_block_analysis failed: %s", exc)
            return None

    def list_block_cache_statuses(self) -> Dict[str, dict]:
        """List statuses for all cached block analyses."""
        statuses: Dict[str, dict] = {}
        try:
            last_eval_key = None
            while True:
                params: dict = {
                    "KeyConditionExpression": Key("pk").eq(self._pk)
                    & Key("sk").begins_with("block_analysis#"),
                    "ProjectionExpression": "sk, block_key, generated_at, schema_version",
                }
                if last_eval_key:
                    params["ExclusiveStartKey"] = last_eval_key

                resp = self.table.query(**params)
                for item in resp.get("Items", []):
                    bk = item.get("block_key")
                    if bk:
                        existing = statuses.get(bk)
                        if not existing or (
                            int(item.get("schema_version", 0)),
                            item.get("generated_at", ""),
                        ) > (
                            int(existing.get("schema_version", 0)),
                            existing.get("generated_at", ""),
                        ):
                            statuses[bk] = item

                last_eval_key = resp.get("LastEvaluatedKey")
                if not last_eval_key:
                    break
        except Exception as exc:
            logger.error("[AnalysisCacheStore] list_block_cache_statuses failed: %s", exc)
        return statuses

    # ── Weekly window analysis ────────────────────────────────────────────────

    def get_window_analysis(
        self,
        window_key: str,
        block_key: Optional[str] = None,
    ) -> Optional[dict]:
        """Read a per-window analysis result. block_key=None means current block."""
        sk = (
            f"weekly_analysis#{window_key}"
            if not block_key
            else f"weekly_analysis#{window_key}#{block_key}"
        )
        try:
            item = self.table.get_item(Key={"pk": self._pk, "sk": sk}).get("Item")
            if not item:
                return None
            data = self._hydrate_item(item)
            if data is None:
                return None
            return {"data": data, "generated_at": item.get("generated_at", "")}
        except Exception as exc:
            logger.error("[AnalysisCacheStore] get_window_analysis failed: %s", exc)
            return None

    def put_window_analysis(
        self,
        window_key: str,
        payload: dict,
        block_key: Optional[str] = None,
        ttl_days: int = CURRENT_BLOCK_TTL_DAYS,
    ) -> None:
        """Write a per-window analysis result to cache."""
        sk = (
            f"weekly_analysis#{window_key}"
            if not block_key
            else f"weekly_analysis#{window_key}#{block_key}"
        )
        effective_ttl = ttl_days if not block_key else None  # past blocks never expire
        try:
            self._put_json_item(sk, payload, ttl_days=effective_ttl)
        except Exception as exc:
            logger.error("[AnalysisCacheStore] put_window_analysis failed: %s", exc)

    # ── Markdown export cache ─────────────────────────────────────────────────

    def get_markdown_cache(self, block_key: str = "current") -> Optional[dict]:
        """Read cached markdown export. Returns {markdown, generated_at} or None."""
        sk = f"markdown_export#{block_key}"
        try:
            item = self.table.get_item(Key={"pk": self._pk, "sk": sk}).get("Item")
            if not item:
                return None
            data = self._hydrate_item(item)
            if not data:
                return None
            # Data may be {"markdown": "..."} or a raw string
            markdown = data.get("markdown", "") if isinstance(data, dict) else str(data)
            if not markdown:
                return None
            return {"markdown": markdown, "generated_at": item.get("generated_at", "")}
        except Exception as exc:
            logger.error("[AnalysisCacheStore] get_markdown_cache failed: %s", exc)
            return None

    def get_markdown_dirty(self, block_key: str = "current") -> Optional[dict]:
        """Read the dirty marker for a markdown export, if present."""
        try:
            item = self.table.get_item(
                Key={"pk": self._pk, "sk": f"markdown_export_dirty#{block_key}"}
            ).get("Item")
            if not item:
                return None
            return {
                "dirty_at": item.get("dirty_at") or item.get("updated_at", ""),
                "reason": item.get("reason", ""),
            }
        except Exception as exc:
            logger.error("[AnalysisCacheStore] get_markdown_dirty failed: %s", exc)
            return None

    def clear_markdown_dirty(self, block_key: str = "current") -> None:
        """Remove the dirty marker after a fresh markdown export is written."""
        try:
            self.table.delete_item(
                Key={"pk": self._pk, "sk": f"markdown_export_dirty#{block_key}"}
            )
        except Exception as exc:
            logger.error("[AnalysisCacheStore] clear_markdown_dirty failed: %s", exc)

    def put_markdown_cache(
        self,
        markdown: str,
        block_key: str = "current",
        ttl_days: int = CURRENT_BLOCK_TTL_DAYS,
    ) -> None:
        """Write markdown export to cache. Past blocks (non-'current') never expire."""
        sk = f"markdown_export#{block_key}"
        effective_ttl = ttl_days if block_key == "current" else None
        try:
            self._put_json_item(sk, {"markdown": markdown}, ttl_days=effective_ttl)
        except Exception as exc:
            logger.error("[AnalysisCacheStore] put_markdown_cache failed: %s", exc)
