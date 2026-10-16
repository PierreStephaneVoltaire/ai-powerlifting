import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import boto3
import pytest

import services.relationships as relationships
from services.dispatch import OperationError
from services.relationships import _expiry, _permissions, _request_item


def test_tied_relationship_expiry_uses_latest_stored_competition_date():
    expiry = _expiry("coach", ["early", "latest"], {"early": "2026-09-01", "latest": "2026-10-12"})
    assert expiry == "2026-10-19T23:59:59.999999+00:00"


def test_coach_and_handler_require_ties_and_peer_is_read_only():
    with pytest.raises(ValueError, match="competition_ties_required"):
        _expiry("handler", [], {})
    with pytest.raises(ValueError, match="peer_grants_are_read_only"):
        _permissions("peer", ["sessions:write"], "write")
    assert _permissions("peer", ["sessions:read"], "write") == ["sessions:read"]


def test_transaction_wire_uses_dynamodb_attribute_values_once(monkeypatch):
    resource = boto3.resource("dynamodb", region_name="ca-central-1", aws_access_key_id="test", aws_secret_access_key="test", endpoint_url="http://127.0.0.1:1")
    table = resource.Table("requests")
    captured = {}

    def capture(params, **_kwargs):
        captured.update(json.loads(params["body"]))
        raise RuntimeError("captured")

    table.meta.client.meta.events.register("before-call.dynamodb.TransactWriteItems", capture)
    monkeypatch.setattr(relationships, "_table", lambda: table)
    with pytest.raises(RuntimeError, match="captured"):
        relationships._transact([{"Put": {"TableName": "requests", "Item": {"pk": "Grant#athlete", "ratio": 1.25}}}])
    item = captured["TransactItems"][0]["Put"]["Item"]
    assert item == {"pk": {"S": "Grant#athlete"}, "ratio": {"N": "1.25"}}


def test_request_uses_authenticated_person_and_stores_requested_permissions():
    request = _request_item(
        {
            "_person_pk": "person-athlete",
            "_access": {"is_self": True, "athlete_pk": "athlete"},
            "athlete_mapped_pk": "athlete",
            "recipient_person_pk": "person-coach",
            "relationship_type": "coach",
            "tied_competition_ids": ["meet"],
            "tied_competition_dates": {"meet": "2026-12-01"},
            "permissions": ["sessions:read", "sessions:write"],
            "scope": "read",
        },
        "request-1",
        "2026-09-14T00:00:00+00:00",
        {"meet": "2026-12-01"},
    )
    assert request["athlete_person_pk"] == "person-athlete"
    assert request["permissions"] == ["sessions:read"]
    assert datetime.fromisoformat(request["expires_at"]).tzinfo == timezone.utc


def test_coach_invitation_keeps_requester_distinct_until_athlete_authorizes(monkeypatch):
    monkeypatch.setattr(relationships, "_athlete_owner", lambda _athlete: {"pk": "athlete-person", "mapped_pk": "athlete"})
    monkeypatch.setattr(relationships, "_requester_role", lambda _person, role: role == "coach")
    request = _request_item(
        {
            "_person_pk": "coach-person",
            "_incoming_invitation": True,
            "athlete_mapped_pk": "athlete",
            "recipient_person_pk": "athlete-person",
            "relationship_type": "coach",
        },
        "incoming-1",
        "2026-09-14T00:00:00+00:00",
    )
    assert request["athlete_person_pk"] == "athlete-person"
    assert request["requester_person_pk"] == "coach-person"
    assert request["recipient_person_pk"] == "athlete-person"
    assert request["permissions"] == []
    assert request["tied_competition_ids"] == []


def test_athlete_approval_authorizes_incoming_scope_and_ties(monkeypatch):
    request = {
        "relationship_id": "incoming-1",
        "state": "pending",
        "athlete_mapped_pk": "athlete",
        "athlete_person_pk": "athlete-person",
        "requester_person_pk": "coach-person",
        "recipient_person_pk": "athlete-person",
        "relationship_type": "coach",
        "scope": "write",
        "permissions": [],
        "tied_competition_ids": [],
        "tied_competition_dates": {},
        "created_at": "2026-09-14T00:00:00+00:00",
    }
    writes = []
    monkeypatch.setattr(relationships, "_legacy_grants", lambda *_args: [])
    monkeypatch.setattr(relationships, "_get", lambda _key: request)
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2027-01-01"})
    monkeypatch.setattr(relationships, "_active_relationship_ids", lambda _athlete, _role: set())
    monkeypatch.setattr(relationships, "_transact", writes.extend)
    result = relationships.respond_request({
        "_person_pk": "athlete-person",
        "relationship_id": "incoming-1",
        "action": "approve",
        "scope": "read",
        "permissions": ["sessions:read", "program:read"],
        "tied_competition_ids": ["meet"],
        "idempotency_key": "approve-incoming",
    })
    assert result["permissions"] == ["program:read", "sessions:read"]
    assert result["tied_competition_ids"] == ["meet"]
    grant = next(action["Put"]["Item"] for action in writes if "Put" in action and action["Put"]["Item"].get("entity") == "grant")
    assert grant["grantee_person_pk"] == "coach-person"
    assert grant["scope"] == "read"
    assert grant["expires_at"] == "2027-01-08T23:59:59.999999+00:00"


def test_slotless_single_legacy_grant_counts_as_active_but_ambiguous_pair_does_not(monkeypatch):
    grants = [{"entity": "grant", "relationship_id": "legacy", "grant_type": "coach", "state": "approved", "tied_competition_ids": ["meet"], "permissions": ["sessions:read"]}]

    class Table:
        def query(self, **_kwargs):
            return {"Items": grants}

    monkeypatch.setattr(relationships, "_table", lambda: Table())
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2027-01-01"})
    assert relationships._active_relationship_ids("athlete", "coach") == {"legacy"}
    grants.append({**grants[0], "relationship_id": "legacy-2"})
    assert relationships._active_relationship_ids("athlete", "coach") == set()


def test_slotless_grantee_key_legacy_grant_requires_explicit_current_relationship(monkeypatch):
    legacy = {
        "pk": "Grant#athlete", "sk": "Grantee#coach#2026-09-01T00:00:00+00:00#coach",
        "grant_type": "coach", "state": "approved", "grantee_mapped_pk": "coach",
        "tied_competition_ids": ["meet"], "permissions": ["sessions:read"],
    }

    class Table:
        def query(self, **_kwargs):
            return {"Items": [legacy]}

    monkeypatch.setattr(relationships, "_table", lambda: Table())
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2027-01-01"})
    identifier = relationships._legacy_relationship_id(legacy)
    assert relationships._active_relationship_ids("athlete", "coach") == {identifier}

    request = {"relationship_id": "new", "state": "pending", "athlete_mapped_pk": "athlete", "athlete_person_pk": "athlete-person", "requester_person_pk": "athlete-person", "recipient_person_pk": "new-coach", "relationship_type": "coach", "scope": "write", "permissions": ["sessions:write"], "tied_competition_ids": ["meet"], "created_at": "2026-09-14T00:00:00+00:00"}
    monkeypatch.setattr(relationships, "_get", lambda key: request if key["pk"] == "Relationship#new" else None)
    monkeypatch.setattr(relationships, "_active_relationship_ids", lambda _athlete, _role: {identifier})
    with pytest.raises(ValueError, match="current_relationship_confirmation_required"):
        relationships.respond_request({"_person_pk": "new-coach", "relationship_id": "new", "action": "approve", "idempotency_key": "approve-new"})


def test_approval_requires_explicit_replacement_for_an_active_role_slot(monkeypatch):
    request = {
        "relationship_id": "new",
        "state": "pending",
        "athlete_mapped_pk": "athlete",
        "athlete_person_pk": "person-athlete",
        "recipient_person_pk": "person-coach",
        "relationship_type": "coach",
        "scope": "write",
        "permissions": ["sessions:write"],
        "tied_competition_ids": ["meet"],
        "tied_competition_dates": {"meet": "2026-12-01"},
        "expires_at": "2026-12-08T23:59:59+00:00",
        "created_at": "2026-09-14T00:00:00+00:00",
    }
    slot = {"state": "active", "relationship_id": "old", "grant_sk": "Relationship#old"}
    monkeypatch.setattr(relationships, "_legacy_grants", lambda *_args: [])
    monkeypatch.setattr(relationships, "_get", lambda key: request if key["pk"] == "Relationship#new" else slot)
    monkeypatch.setattr(relationships, "_slot_is_active", lambda _slot, _athlete: True)
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2026-12-01"})
    with pytest.raises(ValueError, match="current_relationship_confirmation_required"):
        relationships.respond_request({"_person_pk": "person-coach", "relationship_id": "new", "action": "approve", "idempotency_key": "approve-1"})


def test_concurrent_approvals_commit_one_active_relationship():
    request = {
        "pk": "Relationship#new",
        "sk": "Record",
        "relationship_id": "new",
        "entity": "relationship_request",
        "state": "pending",
        "athlete_mapped_pk": "athlete",
        "athlete_person_pk": "person-athlete",
        "recipient_person_pk": "person-coach",
        "relationship_type": "coach",
        "scope": "write",
        "permissions": ["sessions:write"],
        "tied_competition_ids": ["meet"],
        "tied_competition_dates": {"meet": "2026-12-01"},
        "expires_at": "2026-12-08T23:59:59+00:00",
        "created_at": "2026-09-14T00:00:00+00:00",
    }

    class Client:
        def __init__(self, items):
            self.items = items
            self.lock = threading.Lock()
            self.calls = 0

        def transact_write_items(self, TransactItems):
            with self.lock:
                self.calls += 1
                for action in TransactItems:
                    operation, body = next(iter(action.items()))
                    key = tuple(body.get("Key", {}).get(name) for name in ("pk", "sk"))
                    if operation == "Update" and "#state=:pending" in body.get("ConditionExpression", ""):
                        if self.items[key].get("state") != "pending":
                            raise RuntimeError("ConditionalCheckFailed")
                    if operation == "Put" and "attribute_not_exists(pk)" in body.get("ConditionExpression", ""):
                        item_key = tuple(body["Item"].get(name) for name in ("pk", "sk"))
                        if item_key in self.items:
                            raise RuntimeError("ConditionalCheckFailed")
                for action in TransactItems:
                    operation, body = next(iter(action.items()))
                    if operation == "Put":
                        item = body["Item"]
                        self.items[tuple(item.get(name) for name in ("pk", "sk"))] = dict(item)
                    elif operation == "Update":
                        key = tuple(body["Key"].get(name) for name in ("pk", "sk"))
                        if key in self.items:
                            self.items[key]["state"] = "approved"

    class Table:
        def __init__(self, items):
            self.items = items
            self.meta = type("Meta", (), {"client": Client(items)})()
            self.barrier = threading.Barrier(2)
            self.slot_barrier = threading.Barrier(2)

        def get_item(self, Key, **_kwargs):
            item = self.items.get(tuple(Key.get(name) for name in ("pk", "sk")))
            snapshot = dict(item) if item else None
            if Key.get("pk") == "Relationship#new":
                self.barrier.wait(timeout=2)
            if Key.get("sk") == "RelationshipSlot#coach":
                self.slot_barrier.wait(timeout=2)
            return {"Item": snapshot}

    items = {(request["pk"], request["sk"]): dict(request)}
    table = Table(items)
    original = relationships._table
    relationships._table = lambda: table
    original_dates = relationships._stored_competition_dates
    relationships._stored_competition_dates = lambda _athlete, _ids: {"meet": "2026-12-01"}
    original_active_ids = relationships._active_relationship_ids
    relationships._active_relationship_ids = lambda _athlete, _role: set()
    try:
        def approve(key):
            return relationships.respond_request({"_person_pk": "person-coach", "relationship_id": "new", "action": "approve", "idempotency_key": key})

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(approve, key) for key in ("approve-a", "approve-b")]
            results = [future.result() for future in futures if not future.exception()]
            failures = [future.exception() for future in futures if future.exception()]
        assert table.meta.client.calls == 2
        assert len(failures) == 1
        assert isinstance(failures[0], OperationError)
        assert failures[0].status == 409
        assert sum(item.get("entity") == "grant" for item in items.values()) == 1
        grant = next(item for item in items.values() if item.get("entity") == "grant")
        assert grant["grantee_person_pk"] == "person-coach"
    finally:
        relationships._table = original
        relationships._stored_competition_dates = original_dates
        relationships._active_relationship_ids = original_active_ids


def test_different_pending_requests_cannot_both_fill_one_coach_slot(monkeypatch):
    def request(identifier):
        return {
            "pk": f"Relationship#{identifier}", "sk": "Record", "relationship_id": identifier,
            "entity": "relationship_request", "state": "pending", "athlete_mapped_pk": "athlete",
            "athlete_person_pk": "person-athlete", "recipient_person_pk": "person-coach",
            "relationship_type": "coach", "scope": "write", "permissions": ["sessions:write"],
            "tied_competition_ids": ["meet"], "tied_competition_dates": {"meet": "2026-12-01"},
            "expires_at": "2026-12-08T23:59:59+00:00", "created_at": "2026-09-14T00:00:00+00:00",
            "requester_person_pk": "person-athlete",
        }

    items = {(request(identifier)["pk"], "Record"): request(identifier) for identifier in ("one", "two")}
    barrier = threading.Barrier(2)
    slot_barrier = threading.Barrier(2)

    class Client:
        def __init__(self):
            self.lock = threading.Lock()

        def transact_write_items(self, TransactItems):
            with self.lock:
                for action in TransactItems:
                    operation, body = next(iter(action.items()))
                    key = tuple(body.get("Key", {}).get(name) for name in ("pk", "sk"))
                    if operation == "Update" and "#state=:pending" in body.get("ConditionExpression", "") and items[key].get("state") != "pending":
                        raise RuntimeError("ConditionalCheckFailed")
                    if operation == "Put" and body.get("Item", {}).get("entity") == "relationship_slot" and (body["Item"].get("pk"), body["Item"].get("sk")) in items:
                        raise RuntimeError("ConditionalCheckFailed")
                for action in TransactItems:
                    operation, body = next(iter(action.items()))
                    key = tuple(body.get("Key", {}).get(name) for name in ("pk", "sk"))
                    if operation == "Update" and key in items:
                        items[key]["state"] = "approved"
                    if operation == "Put" and body.get("Item", {}).get("entity") in ("grant", "relationship_slot"):
                        item = body["Item"]
                        items[(item["pk"], item["sk"])] = dict(item)

    class Table:
        def __init__(self):
            self.meta = type("Meta", (), {"client": Client()})()

        def get_item(self, Key, **_kwargs):
            if Key.get("pk", "").startswith("Relationship#") and Key.get("sk") == "Record":
                barrier.wait(timeout=2)
            if Key.get("sk") == "RelationshipSlot#coach":
                slot_barrier.wait(timeout=2)
            return {"Item": dict(items[tuple(Key.get(name) for name in ("pk", "sk"))])} if tuple(Key.get(name) for name in ("pk", "sk")) in items else {}

        def query(self, **_kwargs):
            return {"Items": []}

    table = Table()
    monkeypatch.setattr(relationships, "_table", lambda: table)
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2026-12-01"})
    monkeypatch.setattr(relationships, "_active_relationship_ids", lambda _athlete, _role: set())
    monkeypatch.setattr(relationships, "_slot_is_active", lambda _slot, _athlete: False)

    def approve(identifier):
        return relationships.respond_request({"_person_pk": "person-coach", "relationship_id": identifier, "action": "approve", "idempotency_key": f"approve-{identifier}"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(approve, identifier) for identifier in ("one", "two")]
        outcomes = [future.exception() for future in futures]
    assert sum(error is None for error in outcomes) == 1
    assert sum(error is not None for error in outcomes) == 1
    assert next(error for error in outcomes if error is not None).status == 409
    assert sum(item.get("entity") == "relationship_slot" for item in items.values()) == 1


def test_terminal_replay_checks_participant_and_idempotency(monkeypatch):
    request = {"relationship_id": "done", "state": "approved", "athlete_person_pk": "athlete-person", "recipient_person_pk": "coach-person", "requester_person_pk": "athlete-person", "athlete_mapped_pk": "athlete", "relationship_type": "coach", "scope": "write", "permissions": ["sessions:write"], "tied_competition_ids": ["meet"], "last_action": "approve", "last_action_key": "approve-1"}
    request["last_action_hash"] = relationships._approval_hash("done", "coach-person", {"scope": "write", "permissions": ["sessions:write"], "tied_competition_ids": ["meet"], "replace_current_relationship_id": ""}, request)
    monkeypatch.setattr(relationships, "_get", lambda _key: request)
    with pytest.raises(ValueError, match="relationship_request_actor_forbidden"):
        relationships.respond_request({"_person_pk": "intruder", "relationship_id": "done", "action": "approve", "idempotency_key": "approve-1"})
    with pytest.raises(ValueError, match="relationship_request_already_decided"):
        relationships.respond_request({"_person_pk": "coach-person", "relationship_id": "done", "action": "approve", "idempotency_key": "different"})
    with pytest.raises(ValueError, match="relationship_request_already_decided"):
        relationships.respond_request({"_person_pk": "coach-person", "relationship_id": "done", "action": "approve", "idempotency_key": "approve-1", "permissions": ["profile:write"]})
    assert relationships.respond_request({"_person_pk": "coach-person", "relationship_id": "done", "action": "approve", "idempotency_key": "approve-1"}) == request


def test_revoke_replay_is_scoped_to_the_original_actor_and_key(monkeypatch):
    request = {"relationship_id": "done", "state": "revoked", "athlete_person_pk": "athlete-person", "recipient_person_pk": "coach-person", "last_action": "revoke", "last_action_key": "revoke-1", "last_action_hash": relationships._action_hash("done", "revoke", "athlete-person", {"action": "revoke"})}
    monkeypatch.setattr(relationships, "_get", lambda _key: request)
    with pytest.raises(ValueError, match="relationship_request_actor_forbidden"):
        relationships.revoke_relationship({"_person_pk": "intruder", "relationship_id": "done", "idempotency_key": "revoke-1"})
    with pytest.raises(ValueError, match="relationship_already_revoked"):
        relationships.revoke_relationship({"_person_pk": "athlete-person", "relationship_id": "done", "idempotency_key": "different"})
    assert relationships.revoke_relationship({"_person_pk": "athlete-person", "relationship_id": "done", "idempotency_key": "revoke-1"}) == request


def test_changed_competition_date_replaces_inactive_slot_with_observed_revision(monkeypatch):
    request = {"relationship_id": "new", "state": "pending", "athlete_mapped_pk": "athlete", "athlete_person_pk": "athlete-person", "requester_person_pk": "athlete-person", "recipient_person_pk": "coach-person", "relationship_type": "coach", "scope": "write", "permissions": ["sessions:write"], "tied_competition_ids": ["meet"], "created_at": "2026-09-01T00:00:00+00:00"}
    slot = {"state": "active", "relationship_id": "old", "grant_sk": "Relationship#old", "revision": 7, "expires_at": "2026-12-08T23:59:59+00:00"}
    writes = []
    monkeypatch.setattr(relationships, "_legacy_grants", lambda *_args: [])
    monkeypatch.setattr(relationships, "_get", lambda key: request if key["pk"] == "Relationship#new" else slot)
    monkeypatch.setattr(relationships, "_slot_is_active", lambda _slot, _athlete: False)
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2026-09-01"})
    monkeypatch.setattr(relationships, "_transact", writes.extend)
    relationships.respond_request({"_person_pk": "coach-person", "relationship_id": "new", "action": "approve", "idempotency_key": "approve-new", "replace_current_relationship_id": "old"})
    slot_write = next(action["Put"] for action in writes if "Put" in action and action["Put"]["Item"].get("entity") == "relationship_slot")
    assert slot_write["Item"]["revision"] == 8
    assert "relationship_id=:observed_relationship" in slot_write["ConditionExpression"]
    assert slot_write["ExpressionAttributeValues"][":observed_revision"] == 7


def test_approval_aliases_reserved_permissions_attribute(monkeypatch):
    request = {
        "pk": "Relationship#new", "sk": "Record", "relationship_id": "new", "state": "pending",
        "athlete_mapped_pk": "athlete", "athlete_person_pk": "athlete-person", "requester_person_pk": "athlete-person",
        "recipient_person_pk": "coach-person", "relationship_type": "coach", "scope": "write",
        "permissions": ["sessions:write"], "tied_competition_ids": ["meet"], "created_at": "2026-09-14T00:00:00+00:00",
    }
    writes = []
    monkeypatch.setattr(relationships, "_get", lambda key: request if key.get("pk") == "Relationship#new" else None)
    monkeypatch.setattr(relationships, "_stored_competition_dates", lambda _athlete, _ids: {"meet": "2026-12-01"})
    monkeypatch.setattr(relationships, "_legacy_grants", lambda _athlete, _role: [])
    monkeypatch.setattr(relationships, "_active_relationship_ids", lambda _athlete, _role: set())
    monkeypatch.setattr(relationships, "_transact", writes.extend)
    relationships.respond_request({"_person_pk": "coach-person", "relationship_id": "new", "action": "approve", "idempotency_key": "approve-new"})
    update = next(action["Update"] for action in writes if "Update" in action and action["Update"]["Key"]["pk"] == "Relationship#new")
    assert "#permissions=:permissions" in update["UpdateExpression"]
    assert update["ExpressionAttributeNames"]["#permissions"] == "permissions"
