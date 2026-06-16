import os
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.resource("dynamodb")
dynamodb_client = boto3.client("dynamodb")

COMP_MASTER_TABLE = os.environ["COMP_MASTER_TABLE"]
COMP_USER_TABLE = os.environ["COMP_USER_TABLE"]
USER_INDEX_TABLE = os.environ["USER_INDEX_TABLE"]

COMP_MASTER_FIELDS = {
    "name",
    "start_date",
    "end_date",
    "federation_label",
    "federation_slug",
    "federation_website_url",
    "venue_name",
    "venue_address",
    "venue_city",
    "venue_state",
    "venue_country",
    "venue_postal_code",
    "website_url",
    "testing_status",
    "registration_status",
    "registration_url",
    "registration_end_date",
    "source_url",
    "source_name",
    "event_type",
    "last_verified_at",
    "cancelled",
    "master_id",
}

_deserializer = TypeDeserializer()


def _from_image(image):
    if not image:
        return {}
    return {k: _deserializer.deserialize(v) for k, v in image.items()}


def _collect_user_partition_keys(table_name):
    paginator = dynamodb_client.get_paginator("scan")
    seen: set[str] = set()
    for page in paginator.paginate(
        TableName=table_name,
        ProjectionExpression="pk, mapped_pk",
    ):
        for item in page.get("Items", []):
            pk = item.get("pk", {}).get("S")
            mapped_pk = item.get("mapped_pk", {}).get("S")
            canonical = mapped_pk or pk
            if canonical:
                seen.add(canonical)
    yield from seen


def _put_copy(table_name, pk, sk, merged):
    table = dynamodb.Table(table_name)
    item = {"pk": pk, "sk": sk, **merged}
    table.put_item(Item=item)


def _build_merged(user_pk, user_sk, master_record, master_fields, is_insert):
    table = dynamodb.Table(COMP_USER_TABLE)
    existing = table.get_item(Key={"pk": user_pk, "sk": user_sk}).get("Item") or {}

    merged = dict(existing)

    for field in master_fields:
        if field in master_record:
            merged[field] = master_record[field]

    if is_insert and "user_status" not in merged:
        merged["user_status"] = "available"

    return merged


def _handle_master_change(master_record, master_id):
    user_sk = f"COMP#{master_id}"

    for user_pk in _collect_user_partition_keys(USER_INDEX_TABLE):
        is_insert = (
            dynamodb.Table(COMP_USER_TABLE)
            .get_item(Key={"pk": user_pk, "sk": user_sk})
            .get("Item")
            is None
        )
        merged = _build_merged(user_pk, user_sk, master_record, COMP_MASTER_FIELDS, is_insert)
        _put_copy(COMP_USER_TABLE, user_pk, user_sk, merged)


def handler(event, context):
    for record in event.get("Records", []):
        event_name = record.get("eventName")
        if event_name not in ("INSERT", "MODIFY"):
            continue

        new_image = _from_image(record["dynamodb"].get("NewImage"))
        pk = new_image.get("pk", "")

        if pk.startswith("COMP#"):
            master_id = pk.split("#", 1)[1] if "#" in pk else pk
            _handle_master_change(new_image, master_id)
        else:
            print(f"[master-sync] ignoring record with unexpected pk: {pk}")

    return {"statusCode": 200}

