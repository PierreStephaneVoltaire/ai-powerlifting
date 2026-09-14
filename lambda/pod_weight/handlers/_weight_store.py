from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError
from cache_invalidation import invalidate_analysis_caches


def _decimalize(value: Any) -> Any:
    if isinstance(value, float): return Decimal(str(value))
    if isinstance(value, dict): return {key: _decimalize(item) for key, item in value.items()}
    if isinstance(value, list): return [_decimalize(item) for item in value]
    return value


def _numberize(value: Any) -> Any:
    if isinstance(value, Decimal): return float(value) if value % 1 else int(value)
    if isinstance(value, dict): return {key: _numberize(item) for key, item in value.items()}
    if isinstance(value, list): return [_numberize(item) for item in value]
    return value


class WeightStore:
    def __init__(self, table_name: str, region: str):
        self.region = region
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    @staticmethod
    def _key(pk: str, version: str) -> dict[str, str]:
        return {"pk": pk, "sk": f"weight_log#{version}"}

    def _read(self, pk: str, version: str) -> dict:
        item = self.table.get_item(Key=self._key(pk, version)).get("Item")
        return _numberize(item or {**self._key(pk, version), "version": version, "entries": [], "updated_at": datetime.now(timezone.utc).isoformat()})

    async def get_log(self, pk: str, version: str) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, self._read, pk, version)

    def _persist(self, log, previous):
        try:
            self.table.put_item(Item=_decimalize(log), ConditionExpression="attribute_not_exists(updated_at) OR updated_at = :previous", ExpressionAttributeValues={":previous": previous})
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                from services.dispatch import OperationError
                raise OperationError(409, "concurrent_update", "Weight Log changed; reload before retrying") from exc
            raise
        invalidate_analysis_caches(log["pk"], region=self.region)

    async def add_entry(self, pk: str, version: str, entry: dict) -> dict:
        def write() -> dict:
            log = self._read(pk, version)
            previous = log["updated_at"]
            entries = [item for item in log.get("entries", []) if item.get("date") != entry["date"]]
            entries.append(entry)
            log.update({"version": version, "entries": sorted(entries, key=lambda item: str(item.get("date", "")), reverse=True), "updated_at": datetime.now(timezone.utc).isoformat()})
            self._persist(log, previous)
            return log
        return await asyncio.get_running_loop().run_in_executor(None, write)

    async def remove_entry(self, pk: str, version: str, date: str) -> dict:
        def write() -> dict:
            log = self._read(pk, version)
            previous = log["updated_at"]
            log.update({"version": version, "entries": [item for item in log.get("entries", []) if item.get("date") != date], "updated_at": datetime.now(timezone.utc).isoformat()})
            self._persist(log, previous)
            return log
        return await asyncio.get_running_loop().run_in_executor(None, write)


def get_store() -> WeightStore:
    return WeightStore(os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"), os.environ.get("AWS_REGION", "ca-central-1"))


def resolve(args: dict) -> tuple[str, str]:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator"), args.get("version") or "current"


def entry_from(args: dict) -> dict:
    entry = dict(args.get("entry") or {})
    if not entry and args.get("date"):
        entry = {key: value for key, value in args.items() if key not in {"pk", "version"}}
    if "weight_kg" in entry and "kg" not in entry: entry["kg"] = entry.pop("weight_kg")
    if not entry.get("date") or not isinstance(entry.get("kg"), (int, float)) or isinstance(entry.get("kg"), bool):
        raise ValueError("entry.date and entry.kg are required")
    return entry
