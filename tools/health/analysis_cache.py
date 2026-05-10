import os
import gzip
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger(__name__)

class AnalysisCacheStore:
    def __init__(self, table_name: Optional[str] = None, pk: str = "operator", region: str = "ca-central-1"):
        self._table_name = table_name or os.environ.get("ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache")
        self._pk = f"analysis#{pk}"
        self._region = region
        self._table = None

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    def get_cached_block_analysis(self, block_key: str) -> Optional[dict]:
        """Find the latest version of this block analysis in DynamoDB."""
        try:
            # Prefix scan for block_analysis#
            resp = self.table.query(
                KeyConditionExpression=Key("pk").eq(self._pk) & Key("sk").begins_with("block_analysis#"),
                FilterExpression=Attr("sk").contains(f"#{block_key}")
            )
            items = resp.get("Items", [])
            if not items:
                return None

            # Sort by schema_version desc, then generated_at desc
            items.sort(key=lambda x: (int(x.get("schema_version", 0)), x.get("generated_at", "")), reverse=True)
            item = items[0]
            
            return self._hydrate_item(item)
        except Exception as e:
            logger.error(f"[AnalysisCacheStore] Failed to read cache: {e}")
            return None

    def _hydrate_item(self, item: dict) -> Optional[dict]:
        payload = item.get("payload_gzip_b64", "")
        shard_count = int(item.get("shard_count", 0))
        sk = item.get("sk", "")

        if not payload and shard_count > 0:
            parts = []
            for i in range(shard_count):
                part_sk = f"{sk}#part#{i:03d}"
                p_resp = self.table.get_item(Key={"pk": self._pk, "sk": part_sk})
                parts.append(p_resp.get("Item", {}).get("payload_gzip_b64", ""))
            payload = "".join(parts)

        if not payload:
            return None

        try:
            decoded = gzip.decompress(base64.b64decode(payload)).decode("utf-8")
            return json.loads(decoded)
        except Exception as e:
            logger.error(f"[AnalysisCacheStore] Failed to decode payload: {e}")
            return None

    def list_block_cache_statuses(self) -> Dict[str, dict]:
        """List statuses for all cached block analyses."""
        statuses = {}
        try:
            last_eval_key = None
            while True:
                params = {
                    "KeyConditionExpression": Key("pk").eq(self._pk) & Key("sk").begins_with("block_analysis#"),
                    "ProjectionExpression": "sk, block_key, source_fingerprint, generated_at, schema_version"
                }
                if last_eval_key:
                    params["ExclusiveStartKey"] = last_eval_key
                
                resp = self.table.query(**params)
                for item in resp.get("Items", []):
                    bk = item.get("block_key")
                    if bk:
                        # Higher versions/newer dates win
                        existing = statuses.get(bk)
                        if not existing or (int(item.get("schema_version", 0)), item.get("generated_at", "")) > (int(existing.get("schema_version", 0)), existing.get("generated_at", "")):
                            statuses[bk] = item
                
                last_eval_key = resp.get("LastEvaluatedKey")
                if not last_eval_key:
                    break
            return statuses
        except Exception as e:
            logger.error(f"[AnalysisCacheStore] Failed to list statuses: {e}")
            return {}
