from __future__ import annotations
import logging
from typing import List, Optional
from datetime import datetime, timezone
import uuid

import boto3
from boto3.dynamodb.conditions import Key

from storage.models import WebhookRecord

logger = logging.getLogger(__name__)


class DynamoDBWebhookStore:

    def __init__(self, table_name: str, region: str = "ca-central-1", pk: str = "operator"):

        self.table_name = table_name
        self._region = region
        self._pk = pk
        self._table = None

    @property
    def table(self):

        if self._table is None:
            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self.table_name)
        return self._table

    @staticmethod
    def _record_to_item(record: WebhookRecord, pk: str) -> dict:

        item = {
            "pk": pk,
            "sk": record.webhook_id,
            "webhook_id": record.webhook_id,
            "conversation_id": record.conversation_id,
            "platform": record.platform,
            "label": record.label,
            "status": record.status,
            "created_at": record.created_at,
            "config_json": record.config_json,
            "pinned_specialist": record.pinned_specialist or "",
            "self_aware": int(bool(record.self_aware)),
        }
        return item

    @staticmethod
    def _item_to_record(item: dict) -> WebhookRecord:

        record = WebhookRecord(
            webhook_id=item["webhook_id"],
            conversation_id=item["conversation_id"],
            platform=item["platform"],
            label=item["label"],
            status=item["status"],
            created_at=item["created_at"],
            config_json=item.get("config_json", ""),
            pinned_specialist=item.get("pinned_specialist", ""),
            self_aware=bool(item.get("self_aware", 0)),
        )
        return record

    def create(self, record: WebhookRecord) -> WebhookRecord:

        if not record.webhook_id:
            record.webhook_id = f"wh_{uuid.uuid4().hex[:12]}"
        if not record.conversation_id:
            record.conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        if not record.created_at:
            record.created_at = datetime.now(timezone.utc).isoformat()

        item = self._record_to_item(record, self._pk)
        self.table.put_item(Item=item)

        logger.info(f"[DynamoDBWebhookStore] Created webhook {record.webhook_id} ({record.platform}, {record.label})")
        return record

    def get(self, webhook_id: str) -> Optional[WebhookRecord]:

        response = self.table.get_item(
            Key={"pk": self._pk, "sk": webhook_id}
        )
        item = response.get("Item")
        if item is None:
            return None
        return self._item_to_record(item)

    def list_all(self) -> List[WebhookRecord]:

        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk)
        )
        items = response.get("Items", [])
        return [self._item_to_record(item) for item in items]

    def list_active(self) -> List[WebhookRecord]:

        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._pk),
            FilterExpression=Key("status").eq("active"),
        )
        items = response.get("Items", [])
        return [self._item_to_record(item) for item in items]

    def deactivate(self, webhook_id: str) -> bool:

        now = datetime.now(timezone.utc).isoformat()
        response = self.table.update_item(
            Key={"pk": self._pk, "sk": webhook_id},
            UpdateExpression="SET #status = :inactive, deactivated_at = :deactivated_at",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":inactive": "inactive",
                ":deactivated_at": now,
            },
            ReturnValues="ALL_NEW",
        )
        updated = response.get("Attributes")
        if updated is None:
            return False

        logger.info(f"[DynamoDBWebhookStore] Deactivated webhook {webhook_id}")
        return True
