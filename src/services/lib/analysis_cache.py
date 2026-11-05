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
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from services.lib.aws import dynamodb_resource

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
            self._table = dynamodb_resource("dynamodb", region_name=self._region).Table(
                self._table_name
            )
        return self._table

    def _hydrate_item(self, item: dict) -> Optional[Any]:
        payload_str = item.get("payload", "")

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
            markdown = data.get("markdown", "") if isinstance(data, dict) else str(data)
            if not markdown:
                return None
            result = {"markdown": markdown, "generated_at": item.get("generated_at", "")}
            if "access_requirements" in item:
                result["access_requirements"] = item["access_requirements"]
            return result
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
        access_requirements: Optional[dict] = None,
    ) -> None:
        """Write markdown export to cache. Past blocks (non-'current') never expire."""
        sk = f"markdown_export#{block_key}"
        effective_ttl = ttl_days if block_key == "current" or block_key.startswith("current#scope#") else None
        extra_fields = {"access_requirements": access_requirements} if access_requirements is not None else None
        try:
            self._put_json_item(sk, {"markdown": markdown}, ttl_days=effective_ttl, extra_fields=extra_fields)
        except Exception as exc:
            logger.error("[AnalysisCacheStore] put_markdown_cache failed: %s", exc)
