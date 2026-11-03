import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key


@dataclass
class Registration:
    label: str
    bot_token: str
    channel_id: str
    webhook_id: str = field(default_factory=lambda: f"wh_{uuid.uuid4().hex[:12]}")
    conversation_id: str = field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}")
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RegistrationStore:
    def __init__(self, table_name: str, partition: str, region: str, table=None):
        self.partition = partition
        self.table = table or boto3.resource("dynamodb", region_name=region).Table(table_name)

    def _item(self, registration: Registration) -> dict:
        return {
            "pk": self.partition,
            "sk": registration.webhook_id,
            "webhook_id": registration.webhook_id,
            "conversation_id": registration.conversation_id,
            "platform": "discord",
            "label": registration.label,
            "status": registration.status,
            "created_at": registration.created_at,
            "config_json": json.dumps({"bot_token": registration.bot_token, "channel_id": registration.channel_id}),
            "pinned_specialist": "",
            "self_aware": 0,
        }

    @staticmethod
    def _registration(item: dict) -> Registration:
        config = json.loads(item.get("config_json") or "{}")
        return Registration(
            label=item["label"],
            bot_token=config["bot_token"],
            channel_id=str(config["channel_id"]),
            webhook_id=item["webhook_id"],
            conversation_id=item["conversation_id"],
            status=item["status"],
            created_at=item["created_at"],
        )

    def create(self, registration: Registration) -> Registration:
        self.table.put_item(Item=self._item(registration))
        return registration

    def get(self, webhook_id: str) -> Registration | None:
        item = self.table.get_item(Key={"pk": self.partition, "sk": webhook_id}).get("Item")
        return self._registration(item) if item and item.get("platform") == "discord" else None

    def list(self, active_only: bool = False) -> list[Registration]:
        query = {"KeyConditionExpression": Key("pk").eq(self.partition)}
        if active_only:
            query["FilterExpression"] = Attr("status").eq("active")
        items = []
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [self._registration(item) for item in items if item.get("platform") == "discord"]

    def deactivate(self, webhook_id: str) -> None:
        self.table.update_item(
            Key={"pk": self.partition, "sk": webhook_id},
            UpdateExpression="SET #status = :inactive",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":inactive": "inactive"},
        )
