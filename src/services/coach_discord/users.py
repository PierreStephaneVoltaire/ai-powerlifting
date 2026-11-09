import time
from dataclasses import dataclass

import boto3
from boto3.dynamodb.conditions import Attr

CACHE_SECONDS = 600


@dataclass(frozen=True)
class Identity:
    person: str
    athlete: str


class UserDirectory:
    def __init__(self, table_name: str, region: str, table=None):
        self.table = table or boto3.resource("dynamodb", region_name=region).Table(table_name)
        self.cache: dict[str, tuple[float, Identity | None]] = {}

    def _scan(self, discord_id: str) -> list[dict]:
        arguments = {"FilterExpression": Attr("discord_id").eq(discord_id), "ProjectionExpression": "pk, mapped_pk, discord_id"}
        items = []
        while True:
            response = self.table.scan(**arguments)
            items.extend(response.get("Items", []))
            if not response.get("LastEvaluatedKey"):
                return items
            arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def resolve(self, discord_id: str | int) -> Identity | None:
        key = str(discord_id)
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        users = [item for item in self._scan(key) if not str(item.get("pk", "")).startswith("Identity#")]
        identity = Identity(person=str(users[0]["pk"]), athlete=str(users[0].get("mapped_pk") or users[0]["pk"])) if len(users) == 1 else None
        self.cache[key] = (time.monotonic(), identity)
        return identity
