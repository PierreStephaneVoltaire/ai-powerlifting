from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from ..settings_get.core import _normalize_settings

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "ca-central-1")).Table(
            os.environ.get("IF_USER_TABLE", "if-user")
        )
    return _table


def _plain(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _identity_key(issuer: str, sub: str) -> str:
    return "Identity#" + hashlib.sha256(f"{issuer}\0{sub}".encode()).hexdigest()


def _scan(table, **kwargs):
    start = None
    while True:
        request = dict(kwargs)
        if start:
            request["ExclusiveStartKey"] = start
        response = table.scan(**request)
        yield from response.get("Items", [])
        start = response.get("LastEvaluatedKey")
        if not start:
            return


def _legacy_person(table, provider: str, issuer: str, sub: str, discord_subjects: list[str]):
    matches = []
    for item in _scan(table, ConsistentRead=True):
        if str(item.get("pk", "")).startswith("Identity#"):
            continue
        exact = item.get("identity_issuer") == issuer and str(item.get("identity_sub", "")) == sub
        legacy_authentik = (provider == "authentik"
            and issuer == os.environ.get("AUTHENTIK_ISSUER_URL", os.environ.get("AUTHENTIK_ISSUER", ""))
            and str(item.get("authentik_sub", "")) == sub
            and item.get("identity_provider", "authentik") == "authentik"
            and not item.get("identity_issuer"))
        verified_discord = bool(item.get("discord_id") and str(item["discord_id"]) in discord_subjects)
        if exact or legacy_authentik or verified_discord:
            matches.append(item)
    if len(matches) > 1:
        raise ValueError("Provider subject is linked to multiple Persons; operator repair required")
    return matches[0] if matches else None


def _settings(item):
    result = _normalize_settings(_plain(item))
    for field in ("identity_issuer", "identity_provider", "identity_sub"):
        if item.get(field):
            result[field] = str(item[field])
    return result


def _resolve_sync(args):
    provider = args["provider"]
    issuer = args["issuer"].strip()
    sub = args["sub"].strip()
    table = _get_table()
    key = _identity_key(issuer, sub)
    pointer = table.get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
    if pointer:
        person = table.get_item(Key={"pk": pointer["mapped_pk"]}, ConsistentRead=True).get("Item")
        if person:
            return {"settings": _settings(person), "created": False}

    person = _legacy_person(table, provider, issuer, sub, args.get("discord_subjects", []))
    if person:
        pointer = {"pk": key, "mapped_pk": person["pk"], "identity_issuer": issuer, "identity_provider": provider, "identity_sub": sub}
        try:
            table.meta.client.transact_write_items(TransactItems=[
                {"Update": {
                    "TableName": table.name,
                    "Key": {"pk": person["pk"]},
                    "UpdateExpression": "SET identity_issuer = if_not_exists(identity_issuer, :issuer), identity_provider = if_not_exists(identity_provider, :provider), identity_sub = if_not_exists(identity_sub, :sub), #roles = if_not_exists(#roles, :roles)",
                    "ExpressionAttributeNames": {"#roles": "roles"},
                    "ExpressionAttributeValues": {":issuer": issuer, ":provider": provider, ":sub": sub, ":roles": ["athlete"]},
                    "ConditionExpression": "attribute_exists(pk)",
                }},
                {"Put": {"TableName": table.name, "Item": pointer, "ConditionExpression": "attribute_not_exists(pk)"}},
            ])
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            winner = table.get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
            if not winner or winner["mapped_pk"] != person["pk"]:
                raise ValueError("Provider subject linkage changed; retry authentication") from exc
        person = table.get_item(Key={"pk": person["pk"]}, ConsistentRead=True)['Item']
        return {"settings": _settings(person), "created": False}

    now = datetime.now(timezone.utc).isoformat()
    display_name = str(args.get("display_name") or "").strip()[:80]
    person_id = uuid.uuid4().hex
    username = f"person_{person_id[:24]}"
    person_pk = username
    person = {
        "pk": person_pk,
        "mapped_pk": person_pk,
        "username": username,
        "identity_issuer": issuer,
        "identity_provider": provider,
        "identity_sub": sub,
        "discord_id": sub if provider == "discord" else "",
        "discord_username": display_name if provider == "discord" else "",
        "avatar_url": args.get("avatar_url") if isinstance(args.get("avatar_url"), str) else None,
        "nickname": username,
        "profile_visibility": "private",
        "display_name": display_name or username,
        "bio": "",
        "public_training_summary_enabled": False,
        "ranking_country": None,
        "ranking_region": None,
        "age_class": "open",
        "sex": None,
        "bodyweight_kg": None,
        "training_maxes": None,
        "federations": [],
        "roles": [],
        "active_role": "athlete",
        "athlete_basics_complete": False,
        "profile_complete": False,
        "created_at": now,
        "updated_at": now,
    }
    pointer = {"pk": key, "mapped_pk": person_pk, "identity_issuer": issuer, "identity_provider": provider, "identity_sub": sub}
    try:
        table.meta.client.transact_write_items(TransactItems=[
            {"Put": {"TableName": getattr(table, "name", os.environ.get("IF_USER_TABLE", "if-user")), "Item": person, "ConditionExpression": "attribute_not_exists(pk)"}},
            {"Put": {"TableName": getattr(table, "name", os.environ.get("IF_USER_TABLE", "if-user")), "Item": pointer, "ConditionExpression": "attribute_not_exists(pk)"}},
        ])
        return {"settings": _settings(person), "created": True}
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        pointer = table.get_item(Key={"pk": key}, ConsistentRead=True).get("Item")
        if not pointer:
            raise
        winner = table.get_item(Key={"pk": pointer["mapped_pk"]}, ConsistentRead=True).get("Item")
        if not winner:
            raise
        return {"settings": _settings(winner), "created": False}


async def identity_resolve(args: dict) -> dict:
    if args.get("provider") not in ("discord", "authentik") or not args.get("issuer") or not args.get("sub"):
        raise ValueError("Verified issuer, provider, and subject are required")
    return await asyncio.get_running_loop().run_in_executor(None, lambda: _resolve_sync(args))
