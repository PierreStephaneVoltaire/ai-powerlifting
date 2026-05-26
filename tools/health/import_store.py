"""DynamoDB-backed store for staged imports.

Imports are temporary items (TTL = 7 days) awaiting user review.
Schema:
    - Import item: pk="operator", sk="import#pending#{uuid}"
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional, Literal

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger(__name__)

class ImportStore:
    """DynamoDB-backed store for staged imports."""

    SK_PREFIX = "import#pending#"

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._table = None

    @property
    def pk(self) -> str:
        return self._pk

    @pk.setter
    def pk(self, value: str) -> None:
        self._pk = value

    @property
    def table(self):
        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self._table_name)
        return self._table

    def _floats_to_decimals(self, obj: Any) -> Any:
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: self._floats_to_decimals(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._floats_to_decimals(v) for v in obj]
        return obj

    def existing_pending_for_type_sync(self, import_type: str) -> dict | None:
        """Find an existing pending import of the given type with status='awaiting_review'."""
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk) & Key("sk").begins_with(self.SK_PREFIX),
            FilterExpression=Attr("import_type").eq(import_type) & Attr("status").eq("awaiting_review")
        )
        items = resp.get("Items", [])
        return items[0] if items else None

    async def existing_pending_for_type(self, import_type: str) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.existing_pending_for_type_sync(import_type)
        )

    def existing_by_hash_sync(self, file_hash: str, import_type: str) -> dict | None:
        """Find an existing import (any status) with the same hash and type."""
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk) & Key("sk").begins_with(self.SK_PREFIX),
            FilterExpression=Attr("source_file_hash").eq(file_hash) & Attr("import_type").eq(import_type)
        )
        items = resp.get("Items", [])
        return items[0] if items else None

    async def existing_by_hash(self, file_hash: str, import_type: str) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.existing_by_hash_sync(file_hash, import_type)
        )

    def stage_import_sync(self, record: dict) -> str:
        """Stage a new import. Enforces the one-pending-per-type invariant."""
        import_type = record.get("import_type")
        if not import_type:
            raise ValueError("import_type is required")
        
        existing = self.existing_pending_for_type_sync(import_type)
        if existing:
            raise RuntimeError(f"An import of type '{import_type}' is already awaiting review. Apply or reject it first.")
        
        import_id = str(uuid.uuid4())
        sk = f"{self.SK_PREFIX}{import_id}"
        
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)
        
        item = {
            **record,
            "pk": self._pk,
            "sk": sk,
            "import_id": import_id,
            "status": "awaiting_review",
            "uploaded_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "ttl": int(expires_at.timestamp())
        }
        
        self.table.put_item(Item=self._floats_to_decimals(item))
        return import_id

    async def stage_import(self, record: dict) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.stage_import_sync(record)
        )

    def get_pending_sync(self, import_id: str) -> dict | None:
        sk = f"{self.SK_PREFIX}{import_id}"
        resp = self.table.get_item(Key={"pk": self._pk, "sk": sk})
        return resp.get("Item")

    async def get_pending(self, import_id: str) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.get_pending_sync(import_id)
        )

    def list_pending_sync(self, import_type: str | None = None) -> list[dict]:
        filter_expr = Attr("status").eq("awaiting_review")
        if import_type:
            filter_expr &= Attr("import_type").eq(import_type)
            
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk) & Key("sk").begins_with(self.SK_PREFIX),
            FilterExpression=filter_expr
        )
        return resp.get("Items", [])

    async def list_pending(self, import_type: str | None = None) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.list_pending_sync(import_type)
        )

    def mark_applied_sync(self, import_id: str, at: str) -> None:
        sk = f"{self.SK_PREFIX}{import_id}"
        self.table.update_item(
            Key={"pk": self._pk, "sk": sk},
            UpdateExpression="SET #s = :s, applied_at = :a",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "applied", ":a": at}
        )

    async def mark_applied(self, import_id: str, at: str) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.mark_applied_sync(import_id, at)
        )

    def mark_rejected_sync(self, import_id: str, reason: str | None) -> None:
        sk = f"{self.SK_PREFIX}{import_id}"
        update_expr = "SET #s = :s, rejected_at = :a"
        attr_vals = {":s": "rejected", ":a": datetime.now(timezone.utc).isoformat()}
        if reason:
            update_expr += ", rejection_reason = :r"
            attr_vals[":r"] = reason
            
        self.table.update_item(
            Key={"pk": self._pk, "sk": sk},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues=attr_vals
        )

    async def mark_rejected(self, import_id: str, reason: str | None) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.mark_rejected_sync(import_id, reason)
        )
