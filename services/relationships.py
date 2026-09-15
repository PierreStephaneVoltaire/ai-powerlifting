from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.conditions import Attr

from services.access import COACH_PERMISSIONS, HANDLER_PERMISSIONS, active_grants, grant_permissions
from .dispatch import OperationError


RELATIONSHIP_TYPES = ("coach", "handler", "peer")
REQUEST_STATES = ("pending", "approved", "rejected", "cancelled", "revoked", "replaced")


def _table():
    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1")).Table(
        os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests")
    )


def _notifications():
    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1")).Table(
        os.getenv("IF_POWERLIFTING_NOTIFICATIONS_TABLE", "if-powerlifting-notifications")
    )


def _dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _dynamo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dynamo(item) for item in value]
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _person(args: dict) -> str:
    value = str(args.get("_person_pk") or "").strip()
    if not value:
        raise ValueError("authenticated_person_required")
    return value


def _idempotency_key(args: dict) -> str:
    value = str(args.get("idempotency_key") or "").strip()
    if not value or len(value) > 200:
        raise ValueError("idempotency_key_required")
    return value


def _action_hash(relationship_id: str, action: str, actor: str = "", payload: dict | None = None) -> str:
    value = {"relationship_id": relationship_id, "action": action, "actor": actor, "payload": payload or {}}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _approval_hash(relationship_id: str, actor: str, args: dict, request: dict | None = None) -> str:
    payload = {
        "relationship_id": relationship_id,
        "actor": actor,
        "requester_person_pk": (request or {}).get("requester_person_pk"),
        "recipient_person_pk": (request or {}).get("recipient_person_pk"),
        "athlete_person_pk": (request or {}).get("athlete_person_pk"),
        "athlete_mapped_pk": (request or {}).get("athlete_mapped_pk"),
        "relationship_type": (request or {}).get("relationship_type"),
        "scope": args.get("scope"),
        "permissions": sorted(args.get("permissions") or []),
        "tied_competition_ids": sorted(args.get("tied_competition_ids") or []),
        "replace_current_relationship_id": args.get("replace_current_relationship_id") or "",
    }
    return hashlib.sha256(f"{relationship_id}:approve:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}".encode()).hexdigest()


def _request_payload_hash(args: dict) -> str:
    fields = {key: args.get(key) for key in ("athlete_mapped_pk", "recipient_person_pk", "relationship_type", "scope", "permissions", "tied_competition_ids", "note", "replace_current_relationship_id")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _safe(value: Any, maximum: int = 128) -> str:
    value = str(value or "").strip()
    if not value or len(value) > maximum:
        raise ValueError("invalid_identifier")
    return value


def _date(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _expiry(role: str, ids: list[str], dates: dict[str, str]) -> str:
    if role == "peer":
        return ""
    if not ids or any(identifier not in dates for identifier in ids):
        raise ValueError("competition_ties_required")
    try:
        latest = max(_date(dates[identifier]) for identifier in ids)
    except (TypeError, ValueError, KeyError):
        raise ValueError("invalid_tied_competition_dates")
    expiry = datetime.combine((latest + timedelta(days=7)).date(), time.max, timezone.utc)
    return expiry.isoformat()


def _permissions(role: str, requested: Any, scope: str) -> list[str]:
    if role == "coach":
        defaults = list(COACH_PERMISSIONS)
    elif role == "handler":
        defaults = list(HANDLER_PERMISSIONS)
    else:
        defaults = [permission for permission in (requested or []) if isinstance(permission, str)]
    values = list(requested) if isinstance(requested, list) else defaults
    allowed = set(COACH_PERMISSIONS)
    result = sorted({value for value in values if value in allowed})
    if role == "peer" and any(not value.endswith(":read") for value in result):
        raise ValueError("peer_grants_are_read_only")
    if scope == "read":
        result = [value for value in result if value.endswith(":read")]
    if not result:
        raise ValueError("permissions_required")
    return result


def _access(args: dict) -> dict:
    value = args.get("_access")
    return value if isinstance(value, dict) else {}


def _athlete(args: dict) -> str:
    access = _access(args)
    return _safe(args.get("athlete_mapped_pk") or access.get("athlete_pk") or args.get("pk"))


def _person_record(identifier: str) -> dict | None:
    from services.access_store import person_record

    return person_record(identifier)


def _athlete_owner(athlete: str) -> dict | None:
    return _person_record(athlete)


def _is_athlete_owner(actor: str, athlete: str) -> bool:
    owner = _athlete_owner(athlete) or {}
    return actor in {str(owner.get("pk") or ""), str(owner.get("mapped_pk") or "")}


def _require_athlete_owner(args: dict, athlete: str) -> None:
    access = _access(args)
    if access and (access.get("is_self") is True and access.get("athlete_pk") == athlete):
        return
    raise ValueError("athlete_owner_required")


def _requester_role(actor: str, role: str) -> bool:
    return role in (_person_record(actor) or {}).get("roles", [])


def _pending_key(athlete: str, requester: str, recipient: str, role: str) -> dict[str, str]:
    value = f"{athlete}:{requester}:{recipient}:{role}"
    digest = hashlib.sha256(value.encode()).hexdigest()
    return {"pk": f"RelationshipPending#{digest}", "sk": "Record"}


def _delegate(request: dict) -> str:
    requester = request.get("requester_person_pk") or request.get("athlete_person_pk")
    if requester and requester != request.get("athlete_person_pk"):
        return str(requester)
    return str(request.get("recipient_person_pk") or request.get("grantee_person_pk") or request.get("grantee_mapped_pk") or "")


def _stored_competition_dates(athlete: str, identifiers: list[str]) -> dict[str, str]:
    if not identifiers:
        return {}
    wanted = set(identifiers)
    table = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ca-central-1")).Table(
        os.getenv("POWERLIFTING_USER_COMPETITIONS_TABLE", "if-powerlifting-user-competitions")
    )
    dates: dict[str, str] = {}
    request = {"KeyConditionExpression": Key("pk").eq(athlete) & Key("sk").begins_with("COMP#"), "ConsistentRead": True}
    while True:
        response = table.query(**request)
        for item in response.get("Items", []):
            value = item.get("date") or item.get("competition_date") or item.get("start_date")
            if not isinstance(value, str):
                continue
            candidates = {str(item.get("id") or ""), str(item.get("competition_id") or ""), str(item.get("master_id") or ""), str(item.get("sk") or "")}
            candidates.update(candidate[5:] for candidate in list(candidates) if candidate.startswith("COMP#"))
            for candidate in candidates & wanted:
                dates[candidate] = value
        key = response.get("LastEvaluatedKey")
        if not key:
            break
        request["ExclusiveStartKey"] = key
    return dates


def _recipient_record(identifier: str) -> dict | None:
    from services.access_store import database, person_record

    table = database().Table(os.getenv("IF_USER_TABLE", "if-user"))
    record = table.get_item(Key={"pk": identifier}, ConsistentRead=True).get("Item")
    return record or person_record(identifier)


def _slot_is_active(slot: dict, athlete: str) -> bool:
    grant_key = {"pk": f"Grant#{athlete}", "sk": str(slot.get("grant_sk") or "")}
    grant = _get(grant_key) if grant_key["sk"] else None
    if not grant:
        return False
    ids = [str(value) for value in grant.get("tied_competition_ids") or []]
    dates = _stored_competition_dates(athlete, ids)
    return grant in active_grants([grant, slot], dates, datetime.now(timezone.utc))


def _active_relationship_ids(athlete: str, role: str) -> set[str]:
    table = _table()
    arguments = {"KeyConditionExpression": Key("pk").eq(f"Grant#{athlete}"), "ConsistentRead": True}
    grants = []
    while True:
        response = table.query(**arguments)
        grants.extend(item for item in response.get("Items", []) if (item.get("grant_type") or "") == role and item.get("entity") != "relationship_slot")
        if not response.get("LastEvaluatedKey"):
            break
        arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    ids = {str(value) for grant in grants for value in grant.get("tied_competition_ids") or []}
    dates = _stored_competition_dates(athlete, sorted(ids))
    result = set()
    for grant in active_grants(grants, dates, datetime.now(timezone.utc)):
        relationship_id = str(grant.get("relationship_id") or "")
        if relationship_id:
            result.add(relationship_id)
        elif _is_legacy_grant(grant):
            result.add(_legacy_relationship_id(grant))
    return result


def _is_legacy_grant(grant: dict) -> bool:
    return bool(str(grant.get("sk") or "").startswith("Grantee#") and not grant.get("relationship_id"))


def _legacy_relationship_id(grant: dict) -> str:
    original = f"{grant.get('pk', '')}:{grant.get('sk', '')}"
    return f"legacy-{hashlib.sha256(original.encode()).hexdigest()}"


def _legacy_grants(athlete: str, role: str) -> list[dict]:
    table = _table()
    if not hasattr(table, "query"):
        return []
    arguments = {"KeyConditionExpression": Key("pk").eq(f"Grant#{athlete}"), "ConsistentRead": True}
    grants = []
    while True:
        response = table.query(**arguments)
        grants.extend(item for item in response.get("Items", []) if (item.get("grant_type") or "") == role and _is_legacy_grant(item))
        if not response.get("LastEvaluatedKey"):
            break
        arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    ids = {str(value) for grant in grants for value in grant.get("tied_competition_ids") or []}
    dates = _stored_competition_dates(athlete, sorted(ids))
    return [grant for grant in grants if grant_permissions(grant, dates, datetime.now(timezone.utc))]


def _legacy_grant(athlete: str, role: str, relationship_id: str) -> dict | None:
    return next((grant for grant in _legacy_grants(athlete, role) if _legacy_relationship_id(grant) == relationship_id), None)


def _request_key(request_id: str) -> dict[str, str]:
    return {"pk": f"Relationship#{request_id}", "sk": "Record"}


def _idempotency_key_item(person: str, key: str) -> dict[str, str]:
    digest = hashlib.sha256(key.encode()).hexdigest()
    return {"pk": f"RelationshipIdempotency#{person}", "sk": f"Request#{digest}"}


def _get(key: dict[str, str]) -> dict | None:
    item = _table().get_item(Key=key, ConsistentRead=True).get("Item")
    return item or None


def _notification_items(person: str, event_id: str, kind: str, payload: dict) -> tuple[dict, dict]:
    now = _now()
    marker = {"pk": f"Event#{event_id}", "sk": "Notification", "event_id": event_id, "created_at": now}
    item = {
        "pk": f"Person#{person}",
        "sk": f"Notification#{now}#{event_id}",
        "notification_id": event_id,
        "event_id": event_id,
        "kind": kind,
        "payload": payload,
        "read_at": None,
        "created_at": now,
        "gsi1pk": f"Event#{event_id}",
        "gsi1sk": "Notification",
    }
    return marker, item


def _notification_writes(person: str, event_id: str, kind: str, payload: dict) -> list[dict]:
    marker, item = _notification_items(person, event_id, kind, payload)
    return [
        {"Put": {"TableName": os.getenv("IF_POWERLIFTING_NOTIFICATIONS_TABLE", "if-powerlifting-notifications"), "Item": _dynamo(marker), "ConditionExpression": "attribute_not_exists(pk)"}},
        {"Put": {"TableName": os.getenv("IF_POWERLIFTING_NOTIFICATIONS_TABLE", "if-powerlifting-notifications"), "Item": _dynamo(item), "ConditionExpression": "attribute_not_exists(pk)"}},
    ]


def _transact(items: list[dict]) -> None:
    _table().meta.client.transact_write_items(TransactItems=_dynamo(items))


def notification_transaction_items(person: str, event_id: str, kind: str, payload: dict) -> list[dict]:
    return _notification_writes(person, event_id, kind, payload)


def _request_item(args: dict, request_id: str, now: str, stored_dates: dict[str, str] | None = None) -> dict:
    role = str(args.get("relationship_type") or args.get("grant_type") or "").strip().lower()
    if role not in RELATIONSHIP_TYPES:
        raise ValueError("invalid_relationship_type")
    athlete = _athlete(args)
    recipient = _safe(args.get("recipient_person_pk"), 256)
    actor = _person(args)
    if recipient == actor:
        raise ValueError("cannot_request_self")
    incoming = bool(args.get("_incoming_invitation"))
    if incoming:
        if not _is_athlete_owner(recipient, athlete):
            raise ValueError("athlete_recipient_required")
        if not _requester_role(actor, role):
            raise ValueError("requester_role_required")
    else:
        _require_athlete_owner(args, athlete)
    raw_ids = args.get("tied_competition_ids") or []
    if not isinstance(raw_ids, list):
        raise ValueError("invalid_tied_competition_ids")
    ids = sorted({_safe(identifier, 128) for identifier in raw_ids})
    dates = stored_dates or {}
    if not isinstance(dates, dict):
        raise ValueError("invalid_tied_competition_dates")
    if role in ("coach", "handler") and not incoming and not ids:
        raise ValueError("competition_ties_required")
    expiry = _expiry(role, ids, dates) if ids else ""
    scope = str(args.get("scope") or "write").lower()
    if scope not in ("read", "write"):
        raise ValueError("invalid_scope")
    permissions = [] if incoming and not args.get("permissions") else _permissions(role, args.get("permissions"), scope)
    owner = _athlete_owner(athlete) if incoming else {}
    owner_person = str(args.get("_athlete_person_pk") or owner.get("pk") or actor)
    delegate = actor if incoming else recipient
    return {
        **_request_key(request_id),
        "entity": "relationship_request",
        "relationship_id": request_id,
        "state": "pending",
        "athlete_mapped_pk": athlete,
        "athlete_person_pk": owner_person,
        "requester_person_pk": actor,
        "recipient_person_pk": recipient,
        "request_direction": "coach_to_athlete" if incoming else "athlete_to_delegate",
        "relationship_type": role,
        "grant_type": role,
        "scope": scope,
        "permissions": permissions,
        "tied_competition_ids": ids,
        "tied_competition_dates": {str(key): str(value) for key, value in dates.items() if str(key) in ids},
        "expires_at": expiry,
        "note": str(args.get("note") or "").strip()[:280],
        "created_at": now,
        "updated_at": now,
        "inbox_pk": f"Inbox#{recipient}",
        "inbox_sk": f"{now}#{request_id}",
        "sent_pk": f"Sent#{actor}",
        "sent_sk": f"{now}#{request_id}",
        "roster_pk": f"Roster#{delegate}",
        "roster_sk": f"{role}#{athlete}#{request_id}",
        "replace_current_relationship_id": str(args.get("replace_current_relationship_id") or ""),
    }


def create_request(args: dict) -> dict:
    key = _idempotency_key(args)
    actor = _person(args)
    payload_hash = _request_payload_hash(args)
    idem_key = _idempotency_key_item(actor, key)
    previous = _get(idem_key)
    if previous and previous.get("request_id"):
        if previous.get("payload_hash") != payload_hash:
            raise ValueError("idempotency_key_reused")
        return _get(_request_key(str(previous["request_id"]))) or previous
    request_id = uuid4().hex
    athlete = _athlete(args)
    raw_ids = args.get("tied_competition_ids") or []
    if not isinstance(raw_ids, list):
        raise ValueError("invalid_tied_competition_ids")
    ids = sorted({_safe(identifier, 128) for identifier in raw_ids})
    role = str(args.get("relationship_type") or args.get("grant_type") or "").strip().lower()
    owner = _athlete_owner(athlete)
    owner_ids = {str(owner.get("pk") or ""), str(owner.get("mapped_pk") or "")} if owner else set()
    incoming = actor not in owner_ids
    recipient_identifier = str(args.get("recipient_person_pk") or "").strip()
    recipient_record = _recipient_record(recipient_identifier)
    if incoming:
        if role == "peer" or not _requester_role(actor, role):
            raise ValueError("requester_role_required")
        if not recipient_record or str(recipient_record.get("pk") or "") not in owner_ids:
            raise ValueError("athlete_recipient_required")
    elif not recipient_record or (role != "peer" and role not in recipient_record.get("roles", [])):
        raise ValueError("recipient_role_required")
    args = {**args, "recipient_person_pk": str(recipient_record.get("pk") or recipient_identifier), "_athlete_person_pk": str(owner.get("pk") or actor)}
    if incoming:
        args["_incoming_invitation"] = True
        stored_dates = {}
    else:
        stored_dates = _stored_competition_dates(athlete, ids)
    pending_key = _pending_key(athlete, actor, args["recipient_person_pk"], role)
    pending = _get(pending_key)
    if pending and pending.get("request_id"):
        existing = _get(_request_key(str(pending["request_id"])))
        if existing and existing.get("state") == "pending":
            return existing
    slot = _get({"pk": f"Grant#{athlete}", "sk": f"RelationshipSlot#{role}"}) if role in ("coach", "handler") and not incoming else None
    legacy = _legacy_grants(athlete, role) if role in ("coach", "handler") and not incoming else []
    if len(legacy) > 1:
        raise ValueError("legacy_relationship_migration_required")
    if slot and slot.get("state") == "active" and _slot_is_active(slot, athlete) and legacy:
        raise ValueError("legacy_relationship_migration_required")
    if slot and slot.get("state") == "active" and _slot_is_active(slot, athlete):
        if str(args.get("replace_current_relationship_id") or "") != str(slot.get("relationship_id") or ""):
            raise ValueError("current_relationship_confirmation_required")
    if role in ("coach", "handler") and not incoming and not slot:
        active_ids = _active_relationship_ids(athlete, role)
        replacement = str(args.get("replace_current_relationship_id") or "")
        if active_ids and replacement not in active_ids:
            raise ValueError("current_relationship_confirmation_required")
    item = _request_item(args, request_id, _now(), stored_dates)
    idem = {**idem_key, "entity": "relationship_idempotency", "request_id": request_id, "payload_hash": payload_hash, "created_at": item["created_at"]}
    recipient = item["recipient_person_pk"]
    writes = [
        {"Put": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Item": _dynamo(item), "ConditionExpression": "attribute_not_exists(pk)"}},
        {"Put": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Item": _dynamo(idem), "ConditionExpression": "attribute_not_exists(pk)"}},
        {"Put": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Item": _dynamo({**pending_key, "entity": "relationship_pending", "request_id": request_id, "created_at": item["created_at"]}), "ConditionExpression": "attribute_not_exists(pk)"}},
    ]
    writes.extend(_notification_writes(recipient, f"relationship:{request_id}:requested", "relationship_requested", {"relationship_id": request_id, "athlete_mapped_pk": item["athlete_mapped_pk"], "relationship_type": item["relationship_type"], "message": f"A {role} relationship request is waiting for your decision."}))
    try:
        _transact(writes)
    except Exception:
        previous = _get(idem_key)
        if previous and previous.get("request_id"):
            return _get(_request_key(str(previous["request_id"]))) or previous
        pending = _get(pending_key)
        if pending and pending.get("request_id"):
            return _get(_request_key(str(pending["request_id"]))) or pending
        raise
    return item


def _state_update(request: dict, state: str, actor: str, action_key: str) -> dict:
    if state not in REQUEST_STATES:
        raise ValueError("invalid_relationship_state")
    if actor not in {request.get("athlete_person_pk"), request.get("requester_person_pk"), request.get("recipient_person_pk")}:
        raise ValueError("relationship_request_actor_forbidden")
    key = str(request.get("last_action_key") or "")
    if request.get("state") != "pending":
        if request.get("state") == state and request.get("last_action") == state and key == action_key and request.get("last_action_hash") == _action_hash(request["relationship_id"], state, actor, {"action": state}):
            return request
        raise ValueError("relationship_request_already_decided")
    requester = request.get("requester_person_pk") or request["athlete_person_pk"]
    owner = requester if state == "cancelled" else request["recipient_person_pk"]
    if actor != owner:
        raise ValueError("relationship_request_actor_forbidden")
    now = _now()
    target = request["recipient_person_pk"] if actor == requester else requester
    event = f"relationship:{request['relationship_id']}:{state}"
    action_hash = _action_hash(request["relationship_id"], state, actor, {"action": state})
    update = {"state": state, "responded_by": actor, "responded_at": now, "updated_at": now, "last_action": state, "last_action_key": action_key, "last_action_hash": action_hash}
    writes = [{"Update": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Key": _dynamo(_request_key(request["relationship_id"])), "UpdateExpression": "SET #state=:state, responded_by=:actor, responded_at=:at, updated_at=:at, last_action=:action, last_action_key=:action_key, last_action_hash=:action_hash", "ConditionExpression": "#state=:pending", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":state": state, ":pending": "pending", ":actor": actor, ":at": now, ":action": state, ":action_key": action_key, ":action_hash": action_hash})}}]
    writes.append({"Delete": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Key": _dynamo(_pending_key(request["athlete_mapped_pk"], requester, request["recipient_person_pk"], request["relationship_type"]))}})
    writes.extend(_notification_writes(target, event, f"relationship_{state}", {"relationship_id": request["relationship_id"], "relationship_type": request["relationship_type"], "athlete_mapped_pk": request["athlete_mapped_pk"], "message": f"Your {request['relationship_type']} relationship request was {state}."}))
    _transact(writes)
    return {**request, **update}


def respond_request(args: dict) -> dict:
    _idempotency_key(args)
    actor = _person(args)
    request_id = _safe(args.get("relationship_id"), 64)
    action = str(args.get("action") or "").strip().lower()
    request = _get(_request_key(request_id))
    if not request:
        raise ValueError("relationship_request_not_found")
    if action in ("cancel", "reject"):
        return _state_update(request, "cancelled" if action == "cancel" else "rejected", actor, str(args.get("idempotency_key")))
    if action != "approve":
        raise ValueError("invalid_relationship_action")
    if actor not in {request.get("athlete_person_pk"), request.get("requester_person_pk"), request.get("recipient_person_pk")}:
        raise ValueError("relationship_request_actor_forbidden")
    requester = request.get("requester_person_pk") or request.get("athlete_person_pk")
    incoming = requester != request.get("athlete_person_pk")
    expected_actor = request.get("athlete_person_pk") if incoming else request.get("recipient_person_pk")
    if actor != expected_actor:
        raise ValueError("relationship_request_actor_forbidden")
    if request.get("state") != "pending":
        replay_args = {
            "scope": args.get("scope") if incoming or args.get("scope") is not None else request.get("scope"),
            "permissions": args.get("permissions") if incoming or args.get("permissions") is not None else request.get("permissions"),
            "tied_competition_ids": args.get("tied_competition_ids") if incoming or args.get("tied_competition_ids") is not None else request.get("tied_competition_ids"),
            "replace_current_relationship_id": args.get("replace_current_relationship_id") if incoming or args.get("replace_current_relationship_id") is not None else request.get("replace_current_relationship_id"),
        }
        if request.get("state") == "approved" and request.get("last_action") == "approve" and request.get("last_action_key") == str(args.get("idempotency_key")) and request.get("last_action_hash") == _approval_hash(request_id, actor, replay_args, request):
            return request
        raise ValueError("relationship_request_already_decided")
    role = request["relationship_type"]
    if incoming:
        if role == "peer" or not isinstance(args.get("permissions"), list) or not args.get("permissions"):
            raise ValueError("athlete_authorization_required")
        if not isinstance(args.get("tied_competition_ids"), list) or not args.get("tied_competition_ids"):
            raise ValueError("competition_ties_required")
        tied_ids = sorted({_safe(identifier, 128) for identifier in args["tied_competition_ids"]})
        scope = str(args.get("scope") or "").lower()
        if scope not in ("read", "write"):
            raise ValueError("athlete_authorization_required")
        permissions = _permissions(role, args["permissions"], scope)
    else:
        tied_ids = [str(value) for value in request.get("tied_competition_ids") or []]
        scope = request["scope"]
        permissions = request["permissions"]
    current_dates = _stored_competition_dates(request["athlete_mapped_pk"], tied_ids)
    current_expiry = _expiry(role, tied_ids, current_dates)
    table_name = os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests")
    grant_key = {"pk": f"Grant#{request['athlete_mapped_pk']}", "sk": f"Relationship#{request_id}"}
    grant = {
        **grant_key,
        "entity": "grant",
        "relationship_id": request_id,
        "state": "approved",
        "athlete_mapped_pk": request["athlete_mapped_pk"],
        "athlete_person_pk": request["athlete_person_pk"],
        "grantee_person_pk": _delegate(request),
        "grantee_mapped_pk": _delegate(request),
        "grant_type": role,
        "scope": scope,
        "permissions": permissions,
        "tied_competition_ids": tied_ids,
        "tied_competition_dates": current_dates,
        "expires_at": current_expiry,
        "created_by": request["athlete_person_pk"],
        "created_at": request["created_at"],
        "updated_at": _now(),
        "revoked_at": None,
        "revoked_by": None,
    }
    slot_key = {"pk": f"Grant#{request['athlete_mapped_pk']}", "sk": f"RelationshipSlot#{role}"}
    slot = _get(slot_key)
    legacy_active = _legacy_grants(request["athlete_mapped_pk"], role) if role in ("coach", "handler") else []
    if len(legacy_active) > 1:
        raise ValueError("legacy_relationship_migration_required")
    if slot and slot.get("state") == "active" and _slot_is_active(slot, request["athlete_mapped_pk"]) and legacy_active:
        raise ValueError("legacy_relationship_migration_required")
    replacement = str((args if incoming else request).get("replace_current_relationship_id") or "")
    if role in ("coach", "handler") and slot and slot.get("state") == "active":
        if _slot_is_active(slot, request["athlete_mapped_pk"]) and replacement != slot.get("relationship_id"):
            raise ValueError("current_relationship_confirmation_required")
    if role in ("coach", "handler") and not slot:
        active_ids = _active_relationship_ids(request["athlete_mapped_pk"], role)
        if active_ids and replacement not in active_ids:
            raise ValueError("current_relationship_confirmation_required")
    old_request = _get(_request_key(replacement)) if replacement else None
    legacy = _legacy_grant(request["athlete_mapped_pk"], role, replacement) if replacement and not old_request else None
    if replacement and (not old_request and not legacy or old_request and (old_request.get("state") != "approved" or old_request.get("athlete_mapped_pk") != request.get("athlete_mapped_pk") or old_request.get("relationship_type") != role)):
        raise ValueError("replacement_relationship_not_found")
    now = _now()
    approval_hash = _approval_hash(request_id, actor, {"scope": scope, "permissions": permissions, "tied_competition_ids": tied_ids, "replace_current_relationship_id": replacement}, request)
    updated_request = {**request, "state": "approved", "responded_by": actor, "responded_at": now, "updated_at": now, "grant_sk": grant_key["sk"], "expires_at": current_expiry, "tied_competition_ids": tied_ids, "tied_competition_dates": current_dates, "scope": scope, "permissions": permissions, "replace_current_relationship_id": replacement, "last_action": "approve", "last_action_key": str(args.get("idempotency_key")), "last_action_hash": approval_hash, "approval_payload_hash": approval_hash}
    writes: list[dict] = [{"Update": {"TableName": table_name, "Key": _dynamo(_request_key(request_id)), "UpdateExpression": "SET #state=:approved, responded_by=:actor, responded_at=:at, updated_at=:at, grant_sk=:grant_sk, expires_at=:expires, tied_competition_ids=:ids, tied_competition_dates=:dates, #scope=:scope, #permissions=:permissions, replace_current_relationship_id=:replacement, last_action=:action, last_action_key=:action_key, last_action_hash=:action_hash, approval_payload_hash=:action_hash", "ConditionExpression": "#state=:pending", "ExpressionAttributeNames": {"#state": "state", "#scope": "scope", "#permissions": "permissions"}, "ExpressionAttributeValues": _dynamo({":approved": "approved", ":pending": "pending", ":actor": actor, ":at": now, ":grant_sk": grant_key["sk"], ":expires": current_expiry, ":ids": tied_ids, ":dates": current_dates, ":scope": scope, ":permissions": permissions, ":replacement": replacement, ":action": "approve", ":action_key": str(args.get("idempotency_key")), ":action_hash": approval_hash})}}, {"Put": {"TableName": table_name, "Item": _dynamo(grant), "ConditionExpression": "attribute_not_exists(pk)"}}, {"Delete": {"TableName": table_name, "Key": _dynamo(_pending_key(request["athlete_mapped_pk"], requester, request["recipient_person_pk"], role))}}]
    if role in ("coach", "handler"):
        if slot and slot.get("state") == "active" and _slot_is_active(slot, request["athlete_mapped_pk"]):
            old_key = {"pk": slot_key["pk"], "sk": slot.get("grant_sk") or f"Relationship#{slot['relationship_id']}"}
            writes.append({"Update": {"TableName": table_name, "Key": _dynamo(old_key), "UpdateExpression": "SET #state=:replaced, replaced_by=:replacement, revoked_at=:at, revoked_by=:actor, updated_at=:at", "ConditionExpression": "relationship_id=:old AND #state=:approved", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":old": slot["relationship_id"], ":approved": "approved", ":replaced": "replaced", ":replacement": request_id, ":at": now, ":actor": request["athlete_person_pk"]})}})
            if old_request:
                writes.append({"Update": {"TableName": table_name, "Key": _dynamo(_request_key(replacement)), "UpdateExpression": "SET #state=:replaced, replaced_by=:replacement, revoked_at=:at, revoked_by=:actor, updated_at=:at", "ConditionExpression": "#state=:approved", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":approved": "approved", ":replaced": "replaced", ":replacement": request_id, ":at": now, ":actor": request["athlete_person_pk"]})}})
                writes.extend(_notification_writes(_delegate(old_request), f"relationship:{replacement}:replaced", "relationship_replaced", {"relationship_id": replacement, "replaced_by": request_id, "relationship_type": role, "athlete_mapped_pk": request["athlete_mapped_pk"], "message": "Your relationship was replaced by a new relationship."}))
        elif legacy:
            legacy_key = {"pk": legacy["pk"], "sk": legacy["sk"]}
            writes.append({"Update": {"TableName": table_name, "Key": _dynamo(legacy_key), "UpdateExpression": "SET #state=:replaced, relationship_id=:relationship, replaced_by=:replacement, revoked_at=:at, revoked_by=:actor, updated_at=:at", "ConditionExpression": "attribute_not_exists(#state) OR #state=:approved", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":approved": "approved", ":replaced": "replaced", ":relationship": replacement, ":replacement": request_id, ":at": now, ":actor": request["athlete_person_pk"]})}})
        observed_relationship = str(slot.get("relationship_id") or "") if slot else ""
        observed_state = str(slot.get("state") or "") if slot else ""
        observed_revision = int(slot.get("revision") or 0) if slot else 0
        slot_item = {**slot_key, "entity": "relationship_slot", "relationship_id": request_id, "grant_sk": grant_key["sk"], "state": "active", "grant_type": role, "athlete_mapped_pk": request["athlete_mapped_pk"], "grantee_person_pk": _delegate(request), "expires_at": current_expiry, "revision": observed_revision + 1, "updated_at": now}
        writes.append({"Put": {"TableName": table_name, "Item": _dynamo(slot_item), "ConditionExpression": "attribute_not_exists(pk) OR (relationship_id=:observed_relationship AND #state=:observed_state AND (revision=:observed_revision OR (attribute_not_exists(revision) AND :observed_revision=:zero)))", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":observed_relationship": observed_relationship, ":observed_state": observed_state, ":observed_revision": observed_revision, ":zero": 0})}})
    writes.extend(_notification_writes(_delegate(request), f"relationship:{request_id}:approved", "relationship_approved", {"relationship_id": request_id, "relationship_type": role, "athlete_mapped_pk": request["athlete_mapped_pk"], "message": f"Your {role} relationship was approved."}))
    try:
        _transact(writes)
    except Exception as exc:
        code = exc.response.get("Error", {}).get("Code", "") if isinstance(exc, ClientError) else ""
        if code in {"TransactionCanceledException", "ConditionalCheckFailedException"} or str(exc) == "ConditionalCheckFailed":
            raise OperationError(409, "relationship_conflict", "Relationship changed; reload before retrying") from exc
        raise
    return updated_request | {"grant": grant}


def revoke_relationship(args: dict) -> dict:
    action_key = _idempotency_key(args)
    actor = _person(args)
    relationship_id = _safe(args.get("relationship_id"), 64)
    request = _get(_request_key(relationship_id))
    if not request:
        raise ValueError("active_relationship_not_found")
    if actor not in {request.get("athlete_person_pk"), request.get("recipient_person_pk")}:
        raise ValueError("relationship_request_actor_forbidden")
    if request.get("state") == "revoked":
        if request.get("last_action") == "revoke" and request.get("last_action_key") == action_key and request.get("last_action_hash") == _action_hash(relationship_id, "revoke", actor, {"action": "revoke"}):
            return request
        raise ValueError("relationship_already_revoked")
    if request.get("state") != "approved":
        raise ValueError("active_relationship_not_found")
    if actor != request.get("athlete_person_pk"):
        raise ValueError("only_athlete_may_revoke")
    now = _now()
    key = {"pk": f"Grant#{request['athlete_mapped_pk']}", "sk": request.get("grant_sk") or f"Relationship#{relationship_id}"}
    action_hash = _action_hash(relationship_id, "revoke", actor, {"action": "revoke"})
    writes = [{"Update": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Key": _dynamo(key), "UpdateExpression": "SET #state=:revoked, revoked_by=:actor, revoked_at=:at, updated_at=:at", "ConditionExpression": "#state=:approved", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":revoked": "revoked", ":approved": "approved", ":actor": actor, ":at": now})}}, {"Update": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Key": _dynamo(_request_key(relationship_id)), "UpdateExpression": "SET #state=:revoked, revoked_by=:actor, revoked_at=:at, updated_at=:at, last_action=:action, last_action_key=:action_key, last_action_hash=:action_hash", "ConditionExpression": "#state=:approved", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":revoked": "revoked", ":approved": "approved", ":actor": actor, ":at": now, ":action": "revoke", ":action_key": action_key, ":action_hash": action_hash})}}]
    requester = request.get("requester_person_pk") or request["athlete_person_pk"]
    writes.append({"Delete": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Key": _dynamo(_pending_key(request["athlete_mapped_pk"], requester, request["recipient_person_pk"], request["relationship_type"]))}})
    slot_key = {"pk": f"Grant#{request['athlete_mapped_pk']}", "sk": f"RelationshipSlot#{request['relationship_type']}"}
    if request["relationship_type"] in ("coach", "handler"):
        writes.append({"Update": {"TableName": os.getenv("IF_POWERLIFTING_REQUESTS_TABLE", "if-powerlifting-requests"), "Key": _dynamo(slot_key), "UpdateExpression": "SET #state=:revoked, updated_at=:at", "ConditionExpression": "relationship_id=:relationship", "ExpressionAttributeNames": {"#state": "state"}, "ExpressionAttributeValues": _dynamo({":revoked": "revoked", ":at": now, ":relationship": relationship_id})}})
    writes.extend(_notification_writes(_delegate(request), f"relationship:{relationship_id}:revoked", "relationship_revoked", {"relationship_id": relationship_id, "relationship_type": request["relationship_type"], "athlete_mapped_pk": request["athlete_mapped_pk"], "message": f"Your {request['relationship_type']} relationship was revoked."}))
    _transact(writes)
    return {**request, "state": "revoked", "revoked_by": actor, "revoked_at": now, "updated_at": now, "last_action": "revoke", "last_action_key": action_key, "last_action_hash": action_hash}


def _query(index: str, key_name: str, key_value: str) -> list[dict]:
    table = _table()
    expression = Key(key_name).eq(key_value)
    arguments = {"IndexName": index, "KeyConditionExpression": expression, "ScanIndexForward": False}
    result = []
    while True:
        response = table.query(**arguments)
        result.extend(item for item in response.get("Items", []) if item.get("entity") == "relationship_request")
        key = response.get("LastEvaluatedKey")
        if not key:
            return result
        arguments["ExclusiveStartKey"] = key


_PUBLIC_REQUEST_FIELDS = (
    "relationship_id", "state", "active", "legacy_relationship", "athlete_mapped_pk", "athlete_person_pk",
    "requester_person_pk", "recipient_person_pk", "request_direction", "relationship_type", "scope",
    "permissions", "tied_competition_ids", "expires_at", "note", "created_at", "updated_at",
    "responded_by", "responded_at", "replaced_by", "revoked_by", "revoked_at", "replace_current_relationship_id",
    "athlete_display_name",
)


def _public_request(item: dict) -> dict:
    return {key: item[key] for key in _PUBLIC_REQUEST_FIELDS if key in item}


def _legacy_request(grant: dict, athlete: str) -> dict:
    owner = _athlete_owner(athlete) or {}
    athlete_person = str(grant.get("athlete_person_pk") or owner.get("pk") or owner.get("mapped_pk") or athlete)
    delegate = str(grant.get("grantee_person_pk") or grant.get("grantee_mapped_pk") or "")
    return {
        "relationship_id": _legacy_relationship_id(grant),
        "state": "approved",
        "active": True,
        "legacy_relationship": True,
        "athlete_mapped_pk": athlete,
        "athlete_person_pk": athlete_person,
        "requester_person_pk": athlete_person,
        "recipient_person_pk": delegate,
        "request_direction": "athlete_to_delegate",
        "relationship_type": grant.get("grant_type"),
        "scope": grant.get("scope") or "read",
        "permissions": list(grant.get("permissions") or []),
        "tied_competition_ids": [str(value) for value in grant.get("tied_competition_ids") or []],
        "expires_at": str(grant.get("expires_at") or ""),
        "note": str(grant.get("note") or ""),
        "created_at": str(grant.get("created_at") or ""),
        "updated_at": str(grant.get("updated_at") or grant.get("created_at") or ""),
    }


def list_requests(args: dict) -> dict:
    from services.access_store import current_context, person_record
    actor = _person(args)
    now = datetime.now(timezone.utc)
    def current(items):
        result = []
        for indexed in items:
            item = _get(_request_key(indexed['relationship_id']))
            if not item or actor not in (item['athlete_person_pk'], item.get('requester_person_pk'), item['recipient_person_pk']):
                continue
            item = dict(item)
            item['active'] = False
            if item['state'] == 'approved':
                dates = _stored_competition_dates(item['athlete_mapped_pk'], item['tied_competition_ids'])
                item['active'] = item['relationship_id'] in _active_relationship_ids(item['athlete_mapped_pk'], item['relationship_type'])
                try:
                    item['expires_at'] = _expiry(item['relationship_type'], item['tied_competition_ids'], dates)
                except ValueError:
                    item['expires_at'] = ''
            access = current_context(actor, item['athlete_mapped_pk'])
            if 'profile:read' in access['permissions']:
                owner = person_record(item['athlete_mapped_pk'])
                if owner:
                    item['athlete_display_name'] = owner.get('display_name') or owner.get('nickname') or item['athlete_mapped_pk']
            result.append(_public_request(item))
        return result
    sent = current(_query(os.getenv('IF_POWERLIFTING_REQUESTS_SENT_INDEX', 'SentIndex'), 'sent_pk', f'Sent#{actor}'))
    received = current(_query(os.getenv('IF_POWERLIFTING_REQUESTS_INBOX_INDEX', 'InboxIndex'), 'inbox_pk', f'Inbox#{actor}'))
    owner = person_record(actor) or {}
    own_athlete = str(owner.get("mapped_pk") or owner.get("pk") or "")
    for role in ("coach", "handler"):
        for grant in _legacy_grants(own_athlete, role) if own_athlete else []:
            sent.append(_legacy_request(grant, own_athlete))
    return {'sent': sent, 'received': received, 'history': sent + received}


def list_relationship_history(args: dict) -> dict:
    result = list_requests(args)
    return {"items": sorted(result["history"], key=lambda item: item.get("created_at", ""), reverse=True)}


def _favorite_key(person: str, athlete: str) -> dict[str, str]:
    return {"pk": f"Favorite#{person}", "sk": f"Athlete#{athlete}"}


def favorite(args: dict) -> dict:
    person = _person(args)
    athlete = _safe(args.get("athlete_mapped_pk"))
    action = str(args.get("action") or "add").lower()
    key = _favorite_key(person, athlete)
    if action == "remove":
        _table().delete_item(Key=key)
        return {"removed": True, "athlete_mapped_pk": athlete}
    if action != "add":
        raise ValueError("invalid_favorite_action")
    item = {**key, "entity": "favorite", "person_pk": person, "athlete_mapped_pk": athlete, "created_at": _now()}
    _table().put_item(Item=_dynamo(item))
    return item


def list_favorites(args: dict) -> dict:
    person = _person(args)
    table = _table()
    arguments = {"KeyConditionExpression": Key("pk").eq(f"Favorite#{person}")}
    items = []
    while True:
        response = table.query(**arguments)
        items.extend(item for item in response.get("Items", []) if item.get("entity") == "favorite")
        key = response.get("LastEvaluatedKey")
        if not key:
            return {"favorites": items}
        arguments["ExclusiveStartKey"] = key


def list_notifications(args: dict) -> dict:
    person = _person(args)
    table = _notifications()
    arguments = {"KeyConditionExpression": Key("pk").eq(f"Person#{person}"), "ScanIndexForward": False}
    items = []
    while True:
        response = table.query(**arguments)
        items.extend(item for item in response.get("Items", []) if item.get("notification_id"))
        key = response.get("LastEvaluatedKey")
        if not key:
            return {"notifications": items, "total": len(items)}
        arguments["ExclusiveStartKey"] = key


def mark_notifications_read(args: dict) -> dict:
    person = _person(args)
    ids = args.get("notification_ids") or []
    if not isinstance(ids, list) or len(ids) > 100:
        raise ValueError("invalid_notification_ids")
    table = _notifications()
    now = _now()
    changed = 0
    for notification_id in ids:
        value = _safe(notification_id, 512)
        arguments = {"KeyConditionExpression": Key("pk").eq(f"Person#{person}"), "FilterExpression": Attr("notification_id").eq(value)}
        while True:
            response = table.query(**arguments)
            for item in response.get("Items", []):
                table.update_item(Key={"pk": item["pk"], "sk": item["sk"]}, UpdateExpression="SET read_at=:at", ExpressionAttributeValues={":at": now})
                changed += 1
            key = response.get("LastEvaluatedKey")
            if not key:
                break
            arguments["ExclusiveStartKey"] = key
    return {"marked": changed}
