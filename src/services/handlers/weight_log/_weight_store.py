from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from botocore.exceptions import ClientError
from services.lib.block_scope import ALL_BLOCKS, active_block_id_for, current_program_for, scope_entries, stamp
from services.lib.cache_invalidation import invalidate_analysis_caches


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
        self.table = dynamodb_resource("dynamodb", region_name=region).Table(table_name)

    @staticmethod
    def _key(pk: str, version: str) -> dict[str, str]:
        return {"pk": pk, "sk": f"weight_log#{version}"}

    def _read(self, pk: str, version: str) -> dict:
        item = self.table.get_item(Key=self._key(pk, version)).get("Item")
        return _numberize(item or {**self._key(pk, version), "version": version, "entries": [], "updated_at": datetime.now(timezone.utc).isoformat()})

    def _scoped(self, log: dict, block_id: str | None = None) -> dict:
        if block_id == ALL_BLOCKS:
            return log
        active = active_block_id_for(log["pk"], self.table)
        program = current_program_for(log["pk"], self.table)
        if not program:
            program = {"meta": {"current_block_id": active}}
        return {**log, "entries": scope_entries(log.get("entries", []), block_id or active, program, "weight_log")}

    async def get_log(self, pk: str, version: str, block_id: str | None = None) -> dict:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: self._scoped(self._read(pk, version), block_id))

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
            active = active_block_id_for(pk, self.table)
            in_active = {id(item) for item in scope_entries(log.get("entries", []), active, current_program_for(pk, self.table), "weight_log")}
            entries = [item for item in log.get("entries", []) if not (id(item) in in_active and item.get("date") == entry["date"])]
            entries.append(stamp(dict(entry), None, active))
            log.update({"version": version, "entries": sorted(entries, key=lambda item: str(item.get("date", "")), reverse=True), "updated_at": datetime.now(timezone.utc).isoformat()})
            self._persist(log, previous)
            return self._scoped(log)
        return await asyncio.get_running_loop().run_in_executor(None, write)

    async def remove_entry(self, pk: str, version: str, date: str) -> dict:
        def write() -> dict:
            log = self._read(pk, version)
            previous = log["updated_at"]
            active = active_block_id_for(pk, self.table)
            in_active = {id(item) for item in scope_entries(log.get("entries", []), active, current_program_for(pk, self.table), "weight_log")}
            log.update({"version": version, "entries": [item for item in log.get("entries", []) if not (id(item) in in_active and item.get("date") == date)], "updated_at": datetime.now(timezone.utc).isoformat()})
            self._persist(log, previous)
            return self._scoped(log)
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
