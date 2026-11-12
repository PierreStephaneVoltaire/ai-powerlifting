import re
import time
from dataclasses import dataclass

import boto3
from services.handlers.user.identity_resolve.core import _identity_key

CACHE_SECONDS = 600


@dataclass(frozen=True)
class Identity:
    person: str
    athlete: str


class UserDirectory:
    def __init__(self, table_name: str, region: str, table=None):
        self.table = table or boto3.resource("dynamodb", region_name=region).Table(table_name)
        self.cache: dict[str, tuple[float, Identity | None]] = {}

    def resolve(self, discord_id: str | int) -> Identity | None:
        key = str(discord_id)
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        identity = None
        issuer = "https://discord.com"
        if re.fullmatch(r"\d{1,32}", key):
            pointer = self.table.get_item(Key={"pk": _identity_key(issuer, key)}, ConsistentRead=True).get("Item")
            if pointer and pointer.get("identity_issuer") == issuer and pointer.get("identity_sub") == key and pointer.get("mapped_pk"):
                person = self.table.get_item(Key={"pk": pointer["mapped_pk"]}, ConsistentRead=True).get("Item")
                if person and person.get("pk") == pointer["mapped_pk"]:
                    identity = Identity(person=str(person["pk"]), athlete=str(person.get("mapped_pk") or person["pk"]))
        self.cache[key] = (time.monotonic(), identity)
        return identity
