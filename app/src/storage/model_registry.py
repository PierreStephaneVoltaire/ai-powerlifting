











from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)

@dataclass
class ModelInfo:


    model_id: str
    context_size: int
    max_output_tokens: int
    input_pricing: List[Dict[str, str]] = field(default_factory=list)
    output_pricing: List[Dict[str, str]] = field(default_factory=list)
    input_modalities: List[str] = field(default_factory=lambda: ["text"])
    output_modalities: List[str] = field(default_factory=lambda: ["text"])
    tool_support: bool = False
    caching_support: bool = False
    zero_data_retention: bool = False
    throughput: Optional[float] = None
    latency: Optional[float] = None
    updated_at: str = ""

    def to_dynamodb_item(self) -> Dict:
        from decimal import Decimal

        def _to_decimal(val):
            return Decimal(str(val)) if val is not None else None

        return {
            "pk": "MODEL",
            "sk": self.model_id,
            "model_id": self.model_id,
            "context_size": self.context_size,
            "max_output_tokens": self.max_output_tokens,
            "input_pricing": self.input_pricing,
            "output_pricing": self.output_pricing,
            "input_modalities": self.input_modalities,
            "output_modalities": self.output_modalities,
            "tool_support": self.tool_support,
            "caching_support": self.caching_support,
            "zero_data_retention": self.zero_data_retention,
            "throughput": _to_decimal(self.throughput),
            "latency": _to_decimal(self.latency),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict) -> ModelInfo:
        def _as_list(val):
            if val is None:
                return []
            if isinstance(val, list):
                return val
            return [val]

        return cls(
            model_id=item.get("model_id", item.get("sk", "")),
            context_size=int(item.get("context_size", 0)),
            max_output_tokens=int(item.get("max_output_tokens", 0)),
            input_pricing=_as_list(item.get("input_pricing", [])),
            output_pricing=_as_list(item.get("output_pricing", [])),
            input_modalities=_as_list(item.get("input_modalities", ["text"])),
            output_modalities=_as_list(item.get("output_modalities", ["text"])),
            tool_support=bool(item.get("tool_support", False)),
            caching_support=bool(item.get("caching_support", False)),
            zero_data_retention=bool(item.get("zero_data_retention", False)),
            throughput=item.get("throughput"),
            latency=item.get("latency"),
            updated_at=item.get("updated_at", ""),
        )

    def avg_price(self) -> float:

        if not self.input_pricing:
            return float("inf")
        total = 0.0
        count = 0
        for ip in self.input_pricing:
            p = ip.get("price", 0) or 0
            total += float(p)
            count += 1
        for op in self.output_pricing:
            p = op.get("price", 0) or 0
            total += float(p)
            count += 1
        return total / max(count, 1)

class ModelRegistry:





    def __init__(self, table_name: str = "if-models", region: str = "ca-central-1"):
        self.table_name = table_name
        self._table = None
        self._cache: Dict[str, ModelInfo] = {}
        self._region = region

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self.table_name)
        return self._table

    def load(self) -> Dict[str, ModelInfo]:

        from botocore.exceptions import ClientError

        try:
            response = self.table.query(
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": "MODEL"},
            )
            items = response.get("Items", [])
        except ClientError as e:
            logger.error(f"[ModelRegistry] Failed to query DynamoDB: {e}")
            raise RuntimeError(f"ModelRegistry failed to load: {e}") from e
        except Exception as e:
            logger.error(f"[ModelRegistry] Unexpected error: {e}")
            raise

        self._cache.clear()
        for item in items:
            try:
                info = ModelInfo.from_dynamodb_item(item)
                self._cache[info.model_id] = info
            except Exception as e:
                logger.warning(f"[ModelRegistry] Skipping invalid item: {e}")

        logger.info(f"[ModelRegistry] Loaded {len(self._cache)} models from {self.table_name}")
        return self._cache

    def get(self, model_id: str) -> Optional[ModelInfo]:
        return self._cache.get(model_id)

    def get_models(self, model_ids: List[str]) -> List[ModelInfo]:
        return [self._cache[mid] for mid in model_ids if mid in self._cache]

    def sort_models(self, model_ids: List[str], strategy: str) -> List[str]:

        known = [(mid, self._cache.get(mid)) for mid in model_ids]
        unknown = [mid for mid, info in known if info is None]
        known = [(mid, info) for mid, info in known if info is not None]

        reverse = strategy.endswith("_desc")

        if strategy.startswith("price_"):
            known.sort(key=lambda pair: pair[1].avg_price(), reverse=reverse)
        elif strategy.startswith("latency_"):
            known.sort(
                key=lambda pair: pair[1].latency if pair[1].latency else float("inf"),
                reverse=reverse,
            )
        elif strategy.startswith("context_size_"):
            known.sort(key=lambda pair: pair[1].context_size, reverse=reverse)
        elif strategy.startswith("throughput_"):
            known.sort(
                key=lambda pair: pair[1].throughput if pair[1].throughput else 0,
                reverse=reverse,
            )

        return [mid for mid, _ in known] + unknown

    def upsert(self, model_info: ModelInfo) -> None:
        self.table.put_item(Item=model_info.to_dynamodb_item())
        self._cache[model_info.model_id] = model_info

    def upsert_batch(self, models: List[ModelInfo]) -> None:
        from botocore.exceptions import ClientError

        if not models:
            return

        dynamodb = boto3.resource("dynamodb", region_name=self._region)
        batch = dynamodb.batch_writer(self.table_name)

        try:
            for model in models:
                batch.put_item(Item=model.to_dynamodb_item())
                self._cache[model.model_id] = model
            logger.info(f"[ModelRegistry] Upserted {len(models)} models")
        except ClientError as e:
            logger.error(f"[ModelRegistry] Batch write failed: {e}")
            raise

    def refresh_endpoint_stats(self, api_key: str) -> int:












        import json as _json

        updated = 0

        for model_id in list(self._cache.keys()):
            try:
                req = urllib.request.Request(
                    f"https://openrouter.ai/api/v1/models/{model_id}/endpoints",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    endpoints = (
                        _json.loads(resp.read())
                        .get("data", {})
                        .get("endpoints", [])
                    )

                latencies = []
                throughputs = []
                for ep in endpoints:
                    lat = ep.get("latency_last_30m", {})
                    thr = ep.get("throughput_last_30m", {})
                    if isinstance(lat, dict) and lat.get("p50"):
                        latencies.append(lat["p50"])
                    if isinstance(thr, dict) and thr.get("p50"):
                        throughputs.append(thr["p50"])

                if not latencies and not throughputs:
                    continue

                best_latency = min(latencies) if latencies else None
                best_throughput = max(throughputs) if throughputs else None

                info = self._cache[model_id]
                info.latency = best_latency
                info.throughput = best_throughput
                info.updated_at = datetime.now(timezone.utc).isoformat()

                self.table.put_item(Item=info.to_dynamodb_item())
                updated += 1

            except Exception as e:
                logger.warning(f"[ModelRegistry] Failed to refresh stats for {model_id}: {e}")

        logger.info(f"[ModelRegistry] Refreshed endpoint stats for {updated} models")
        return updated
