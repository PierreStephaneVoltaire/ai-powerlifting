import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.access_store import pages, person_record


def relationship_id(item: dict) -> str:
    original = f"{item.get('pk', '')}:{item.get('sk', '')}"
    return f"legacy-{hashlib.sha256(original.encode()).hexdigest()}"


def canonical(item: dict) -> dict:
    identifier = relationship_id(item)
    grant_key = {"pk": item["pk"], "sk": f"Relationship#{identifier}"}
    athlete = str(item.get("athlete_mapped_pk") or str(item.get("pk") or "").removeprefix("Grant#"))
    owner = person_record(athlete) or {}
    owner_person = str(item.get("athlete_person_pk") or owner.get("pk") or "")
    grantee_mapped = str(item.get("grantee_mapped_pk") or "")
    grantee = person_record(str(item.get("grantee_person_pk") or grantee_mapped)) or {}
    grantee_person = str(item.get("grantee_person_pk") or grantee.get("pk") or "")
    return {
        **item,
        **grant_key,
        "entity": "grant",
        "relationship_id": identifier,
        "state": "approved",
        "athlete_mapped_pk": athlete,
        "athlete_person_pk": owner_person,
        "grantee_person_pk": grantee_person,
        "grant_sk": grant_key["sk"],
        "original_grant_key": {"pk": item["pk"], "sk": item["sk"]},
        "updated_at": str(item.get("updated_at") or datetime.now(timezone.utc).isoformat()),
    }


def request_record(grant: dict, result: dict) -> dict | None:
    athlete_person = result.get("athlete_person_pk")
    grantee_person = result.get("grantee_person_pk")
    if not athlete_person or not grantee_person:
        return None
    now = result.get("updated_at") or result.get("created_at") or datetime.now(timezone.utc).isoformat()
    role = str(result.get("grant_type") or "")
    return {
        "pk": f"Relationship#{result['relationship_id']}",
        "sk": "Record",
        "entity": "relationship_request",
        "relationship_id": result["relationship_id"],
        "state": "approved",
        "athlete_mapped_pk": result["athlete_mapped_pk"],
        "athlete_person_pk": athlete_person,
        "requester_person_pk": athlete_person,
        "recipient_person_pk": grantee_person,
        "request_direction": "athlete_to_delegate",
        "relationship_type": role,
        "grant_type": role,
        "scope": result.get("scope") or "read",
        "permissions": list(result.get("permissions") or []),
        "tied_competition_ids": [str(value) for value in result.get("tied_competition_ids") or []],
        "tied_competition_dates": dict(result.get("tied_competition_dates") or {}),
        "expires_at": str(result.get("expires_at") or ""),
        "note": str(result.get("note") or ""),
        "created_at": str(result.get("created_at") or now),
        "updated_at": str(now),
        "responded_by": athlete_person,
        "responded_at": str(result.get("updated_at") or now),
        "grant_sk": result["sk"],
        "inbox_pk": f"Inbox#{grantee_person}",
        "inbox_sk": f"{now}#{result['relationship_id']}",
        "sent_pk": f"Sent#{athlete_person}",
        "sent_sk": f"{now}#{result['relationship_id']}",
        "roster_pk": f"Roster#{grantee_person}",
        "roster_sk": f"{role}#{result['athlete_mapped_pk']}#{result['relationship_id']}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Add canonical relationship records beside legacy grants.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    table_name = os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests")
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1")).Table(table_name)
    grants = pages(table, "scan", FilterExpression=Attr("pk").begins_with("Grant#"), ConsistentRead=True)
    for item in grants:
        role = str(item.get("grant_type") or "")
        if role not in ("coach", "handler") or not str(item.get("sk") or "").startswith("Grantee#") or item.get("relationship_id"):
            continue
        if item.get("revoked_at") or str(item.get("state") or "approved") != "approved":
            continue
        result = canonical(item)
        slot = {
            "pk": item["pk"],
            "sk": f"RelationshipSlot#{role}",
            "entity": "relationship_slot",
            "relationship_id": result["relationship_id"],
            "grant_sk": result["sk"],
            "state": "active",
            "grant_type": role,
            "athlete_mapped_pk": result["athlete_mapped_pk"],
            "grantee_person_pk": result["grantee_person_pk"],
            "expires_at": result.get("expires_at") or "",
            "updated_at": result["updated_at"],
            "revision": 1,
        }
        request = request_record(item, result)
        print(f"{'Canonicalizing' if args.apply else 'Would canonicalize'} {item['pk']} {item['sk']} as {result['relationship_id']}")
        if not args.apply:
            continue
        try:
            table.put_item(Item=result, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
        try:
            table.put_item(Item=slot, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
        if request:
            try:
                table.put_item(Item=request, ConditionExpression="attribute_not_exists(pk)")
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise


if __name__ == "__main__":
    main()
