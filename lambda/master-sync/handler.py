import os
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.resource("dynamodb")
dynamodb_client = boto3.client("dynamodb")

COMP_MASTER_TABLE = os.environ["COMP_MASTER_TABLE"]
COMP_USER_TABLE = os.environ["COMP_USER_TABLE"]
FED_MASTER_TABLE = os.environ["FED_MASTER_TABLE"]
FED_USER_TABLE = os.environ["FED_USER_TABLE"]
USER_INDEX_TABLE = os.environ["USER_INDEX_TABLE"]

# Master-controlled fields that the master-sync Lambda owns on per-user copies.
# Anything not in these sets is considered user-owned and must never be touched.
COMP_MASTER_FIELDS = {
    "name",
    "start_date",
    "end_date",
    "federation_id",
    "federation_label",
    "federation_slug",
    "federation_website_url",
    "venue_name",
    "venue_address",
    "venue_city",
    "venue_state",
    "venue_country",
    "venue_postal_code",
    "venue_latitude",
    "venue_longitude",
    "venue_coordinate_quality",
    "website_url",
    "testing_status",
    "registration_status",
    "registration_url",
    "registration_end_date",
    "source_url",
    "source_name",
    "event_type",
    "last_verified_at",
    "confidence_status",
    "cancelled",
    "master_id",
}

FED_MASTER_FIELDS = {
    "name",
    "abbreviation",
    "region",
    "website_url",
    "master_id",
}

USER_STATUS_DEFAULTS = {
    "COMP#": "available",
    "FED#": "active",
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
      - user_status: default ('available' for comps, 'active' for federations)
        ONLY when the user copy is being created for the first time.
    """
    table = dynamodb.Table(_user_table_for_sk(user_sk))
    existing = table.get_item(Key={"pk": user_pk, "sk": user_sk}).get("Item") or {}

    merged = dict(existing)  # start with whatever the user already has

    # Overwrite master-controlled fields from the new master record
    for field in master_fields:
        if field in master_record:
            merged[field] = master_record[field]

    # user_status default only applies on first insert
    if is_insert and "user_status" not in merged:
        for prefix, default in USER_STATUS_DEFAULTS.items():
            if user_sk.startswith(prefix):
                merged["user_status"] = default
                break

    return merged


def _user_table_for_sk(sk):
    if sk.startswith("COMP#"):
        return COMP_USER_TABLE
    if sk.startswith("FED#"):
        return FED_USER_TABLE
    raise ValueError(f"Unknown user-copy sk prefix: {sk}")


def _handle_master_change(master_record, user_table, master_fields, sk_prefix, master_id):
    """
    Fan one master record out to every user's per-user copy.
    master_id is the bare id (no prefix) for the user's sk.
    """
    user_sk = f"{sk_prefix}{master_id}"

    for user_pk in _scan_user_pks(USER_INDEX_TABLE):
        is_insert = (
            dynamodb.Table(user_table)
            .get_item(Key={"pk": user_pk, "sk": user_sk})
            .get("Item")
            is None
        )
        merged = _build_merged(user_pk, user_sk, master_record, master_fields, is_insert)
        _put_copy(user_table, user_pk, user_sk, merged)


def handler(event, context):
    """DynamoDB stream handler — fan master comp/federation changes to per-user copies."""
    for record in event.get("Records", []):
        event_name = record.get("eventName")
        if event_name not in ("INSERT", "MODIFY"):
            # REMOVE on a master row leaves existing user copies untouched.
            continue

        new_image = _from_image(record["dynamodb"].get("NewImage"))
        pk = new_image.get("pk", "")
        master_id = pk.split("#", 1)[1] if "#" in pk else pk

        if pk.startswith("COMP#"):
            _handle_master_change(
                master_record=new_image,
                user_table=COMP_USER_TABLE,
                master_fields=COMP_MASTER_FIELDS,
                sk_prefix="COMP#",
                master_id=master_id,
            )
        elif pk.startswith("FED#"):
            _handle_master_change(
                master_record=new_image,
                user_table=FED_USER_TABLE,
                master_fields=FED_MASTER_FIELDS,
                sk_prefix="FED#",
                master_id=master_id,
            )
        else:
            print(f"[master-sync] ignoring record with unexpected pk: {pk}")

    return {"statusCode": 200}
