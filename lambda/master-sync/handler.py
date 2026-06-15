import os
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.resource("dynamodb")
dynamodb_client = boto3.client("dynamodb")

COMP_MASTER_TABLE = os.environ["COMP_MASTER_TABLE"]
COMP_USER_TABLE = os.environ["COMP_USER_TABLE"]
USER_INDEX_TABLE = os.environ["USER_INDEX_TABLE"]

# Master-controlled fields that the master-sync Lambda owns on per-user copies.
# Anything not in these sets is considered user-owned and must never be touched.
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
    """Convert a DynamoDB Stream Image (low-level dict) into a plain dict."""
    if not image:
        return {}
    return {k: _deserializer.deserialize(v) for k, v in image.items()}


def _scan_user_pks(table_name):
    """Yield every pk in the user index table. These pks identify each user."""
    paginator = dynamodb_client.get_paginator("scan")
    for page in paginator.paginate(TableName=table_name, ProjectionExpression="pk"):
        for item in page.get("Items", []):
            pk = item.get("pk", {}).get("S")
            if pk:
                yield pk


def _put_copy(table_name, pk, sk, merged):
    """PutItem with merged payload. boto3 high-level resource handles Decimal coercion."""
    table = dynamodb.Table(table_name)
    item = {"pk": pk, "sk": sk, **merged}
    # boto3 resource auto-converts float→Decimal; we passed raw values from the
    # stream deserializer which is already Decimal-safe.
    table.put_item(Item=item)


def _build_merged(user_pk, user_sk, master_record, master_fields, is_insert):
    """
    Read the existing user copy (if any), then merge:
      - master-controlled fields: overwritten from master record
      - user-owned fields: preserved as-is
      - user_status: default 'available' ONLY when the user copy is being created
        for the first time.
    """
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
    """
    Fan one master competition out to every user's per-user copy.
    master_id is the bare id (no prefix) for the user's sk.
    """
    user_sk = f"COMP#{master_id}"

    for user_pk in _scan_user_pks(USER_INDEX_TABLE):
        is_insert = (
            dynamodb.Table(COMP_USER_TABLE)
            .get_item(Key={"pk": user_pk, "sk": user_sk})
            .get("Item")
            is None
        )
        merged = _build_merged(user_pk, user_sk, master_record, COMP_MASTER_FIELDS, is_insert)
        _put_copy(COMP_USER_TABLE, user_pk, user_sk, merged)


def handler(event, context):
    """DynamoDB stream handler — fan master competition changes to per-user copies."""
    for record in event.get("Records", []):
        event_name = record.get("eventName")
        if event_name not in ("INSERT", "MODIFY"):
            # REMOVE on a master row leaves existing user copies untouched.
            continue

        new_image = _from_image(record["dynamodb"].get("NewImage"))
        pk = new_image.get("pk", "")

        if pk.startswith("COMP#"):
            master_id = pk.split("#", 1)[1] if "#" in pk else pk
            _handle_master_change(new_image, master_id)
        else:
            print(f"[master-sync] ignoring record with unexpected pk: {pk}")

    return {"statusCode": 200}

