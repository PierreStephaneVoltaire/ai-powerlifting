from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3
from services.lib.aws import dynamodb_resource, client as aws_client
from boto3.dynamodb.conditions import Attr, Key


class ImportStore:
    SK_PREFIX = "import#pending#"

    def __init__(self, table_name: str, pk: str = "operator", region: str = "ca-central-1"):
        self._table_name = table_name
        self._pk = pk
        self._region = region
        self._table = None

    @property
    def pk(self):
        return self._pk

    @pk.setter
    def pk(self, value):
        self._pk = value

    @property
    def table(self):
        if self._table is None:
            self._table = dynamodb_resource("dynamodb", region_name=self._region).Table(self._table_name)
        return self._table

    @staticmethod
    def _floats_to_decimals(value: Any) -> Any:
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, dict):
            return {key: ImportStore._floats_to_decimals(item) for key, item in value.items()}
        if isinstance(value, list):
            return [ImportStore._floats_to_decimals(item) for item in value]
        return value

    def _query(self, filter_expression=None, prefix=SK_PREFIX):
        kwargs = {
            "KeyConditionExpression": Key("pk").eq(self._pk) & Key("sk").begins_with(prefix),
        }
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        return self.table.query(**kwargs).get("Items", [])

    def stage_import_sync(self, record: dict) -> str:
        import_type = record.get("import_type")
        if not import_type:
            raise ValueError("import_type is required")
        if self._query(Attr("import_type").eq(import_type) & Attr("status").eq("awaiting_review")):
            raise RuntimeError(f"An import of type '{import_type}' is already awaiting review. Apply or reject it first.")
        import_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        item = {
            **record,
            "pk": self._pk,
            "sk": f"{self.SK_PREFIX}{import_id}",
            "import_id": import_id,
            "status": "awaiting_review",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
            "ttl": int(expires_at.timestamp()),
        }
        self.table.put_item(Item=self._floats_to_decimals(item))
        return import_id

    async def stage_import(self, record):
        return await asyncio.to_thread(self.stage_import_sync, record)

    def existing_by_hash_sync(self, file_hash, import_type):
        return next(iter(self._query(Attr("source_file_hash").eq(file_hash) & Attr("import_type").eq(import_type))), None)

    async def existing_by_hash(self, file_hash, import_type):
        return await asyncio.to_thread(self.existing_by_hash_sync, file_hash, import_type)

    def claim_apply_sync(self, import_id, claim_id, at):
        return self.table.update_item(
            Key={"pk": self._pk, "sk": f"{self.SK_PREFIX}{import_id}"},
            UpdateExpression="SET #status = :applying, applying_at = :at, apply_claim_id = :claim",
            ConditionExpression=Attr("status").eq("awaiting_review"),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":applying": "applying", ":at": at, ":claim": claim_id},
            ReturnValues="ALL_NEW",
        ).get("Attributes")

    async def claim_apply(self, import_id, claim_id, at):
        return await asyncio.to_thread(self.claim_apply_sync, import_id, claim_id, at)

    def get_pending_sync(self, import_id):
        return self.table.get_item(Key={"pk": self._pk, "sk": f"{self.SK_PREFIX}{import_id}"}).get("Item")

    async def get_pending(self, import_id):
        return await asyncio.to_thread(self.get_pending_sync, import_id)

    def list_pending_sync(self, import_type=None):
        filter_expression = Attr("status").eq("awaiting_review")
        if import_type:
            filter_expression &= Attr("import_type").eq(import_type)
        return self._query(filter_expression)

    async def list_pending(self, import_type=None):
        return await asyncio.to_thread(self.list_pending_sync, import_type)

    def list_imports_sync(self):
        return self._query(prefix="import#")

    async def list_imports(self):
        return await asyncio.to_thread(self.list_imports_sync)

    def mark_applied_sync(self, import_id, at, claim_id=None):
        kwargs = {
            "Key": {"pk": self._pk, "sk": f"{self.SK_PREFIX}{import_id}"},
            "UpdateExpression": "SET #status = :status, applied_at = :at",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":status": "applied", ":at": at},
        }
        if claim_id:
            kwargs["ConditionExpression"] = Attr("status").eq("applying") & Attr("apply_claim_id").eq(claim_id)
        self.table.update_item(**kwargs)

    async def mark_applied(self, import_id, at, claim_id=None):
        await asyncio.to_thread(self.mark_applied_sync, import_id, at, claim_id)

    def mark_uncertain_sync(self, import_id, claim_id, reason):
        self.table.update_item(
            Key={"pk": self._pk, "sk": f"{self.SK_PREFIX}{import_id}"},
            UpdateExpression="SET #status = :status, uncertain_at = :at, uncertainty_reason = :reason",
            ConditionExpression=Attr("status").eq("applying") & Attr("apply_claim_id").eq(claim_id),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": "uncertain", ":at": datetime.now(timezone.utc).isoformat(), ":reason": reason[:1000]},
        )

    async def mark_uncertain(self, import_id, claim_id, reason):
        await asyncio.to_thread(self.mark_uncertain_sync, import_id, claim_id, reason)

    def mark_rejected_sync(self, import_id, reason=None):
        expression = "SET #status = :status, rejected_at = :at"
        values = {":status": "rejected", ":at": datetime.now(timezone.utc).isoformat()}
        if reason:
            expression += ", rejection_reason = :reason"
            values[":reason"] = reason
        self.table.update_item(
            Key={"pk": self._pk, "sk": f"{self.SK_PREFIX}{import_id}"},
            UpdateExpression=expression,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=values,
        )

    async def mark_rejected(self, import_id, reason=None):
        await asyncio.to_thread(self.mark_rejected_sync, import_id, reason)
