from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
from threading import Lock

import boto3
import pytest
from botocore.exceptions import ClientError

from services.authored_notes import AuthoredNotesStore, NoteConflict, NoteForbidden, NoteIdempotencyConflict, NoteNotFound


class FakeTable:
    def __init__(self):
        self.items = {}
        self.lock = Lock()
        self.calls = []
        self.name = "if-health"
        self.meta = SimpleNamespace(client=SimpleNamespace(transact_write_items=self.transact_write_items))
        self.lose_next = False

    def get_item(self, Key, **kwargs):
        with self.lock:
            item = self.items.get((Key["pk"], Key["sk"]))
            return {"Item": dict(item)} if item else {}

    def query(self, KeyConditionExpression=None, **kwargs):
        pk = KeyConditionExpression._values[0]._values[1]
        with self.lock:
            return {"Items": [dict(item) for (item_pk, _), item in self.items.items() if item_pk == pk]}

    def transact_write_items(self, TransactItems):
        with self.lock:
            for action in TransactItems:
                if "Put" in action:
                    put = action["Put"]
                    item = put["Item"]
                    if put.get("ConditionExpression") and (item["pk"], item["sk"]) in self.items:
                        raise self._conditional()
                else:
                    update = action["Update"]
                    key = update["Key"]
                    item = self.items.get((key["pk"], key["sk"]))
                    values = update["ExpressionAttributeValues"]
                    if not item:
                        raise self._conditional()
                    expected = values.get(":expected_revision", values.get(":expected"))
                    if expected is not None and item.get("revision", item.get("attachment_revision", 0)) != expected:
                        raise self._conditional()
                    if ":attached" in values and item.get("detached") is not values[":attached"]:
                        raise self._conditional()
                    names = update.get("ExpressionAttributeNames", {})
                    for alias, field in names.items():
                        placeholder = ":" + alias.removeprefix("#")
                        if placeholder in values:
                            item[field] = values[placeholder]
                    self.items[(key["pk"], key["sk"])] = item
            for action in TransactItems:
                if "Put" in action:
                    item = action["Put"]["Item"]
                    self.items[(item["pk"], item["sk"])] = dict(item)
            self.calls.extend([action.get("Update", {}).get("ExpressionAttributeValues", {}) for action in TransactItems])
            if self.lose_next:
                self.lose_next = False
                raise RuntimeError("response lost after commit")

    @staticmethod
    def _conditional():
        return ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "condition"}}, "UpdateItem")


def mutation(revision, key):
    return {"text": "private words", "expected_revision": revision, "idempotency_key": key}


def access(*permissions, is_self=False, own_athlete_pk="athlete"):
    return {"permissions": list(permissions), "is_self": is_self, "own_athlete_pk": own_athlete_pk}


def test_authored_note_boundaries_and_immutable_attachment():
    table = FakeTable()
    store = AuthoredNotesStore(table=table)
    created = store.save_private("author", mutation(0, "create"))
    assert store.save_private("author", mutation(0, "create")) == created
    shared = store.share("athlete", "author", {"note_id": created["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": "share"}, access("program:write"))
    assert store.share("athlete", "author", {"note_id": created["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": "share"}, access("program:write")) == shared
    edited = store.save_private("author", {"note_id": created["note_id"], **mutation(1, "edit")})
    assert edited["revision"] == 2
    listed = store.list_attachments("athlete", {"context_domain": "program"}, access("program:read"))
    assert listed["attachments"][0]["text"] == "private words"
    assert shared["source_revision"] == 1
    with pytest.raises(NoteConflict):
        store.save_private("athlete", {"note_id": created["note_id"], **mutation(1, "forged")})
    with pytest.raises(NoteForbidden):
        store.share("athlete", "author", {"note_id": created["note_id"], "wanted_revision": 2, "context_domain": "program", "expected_attachment_revision": 1, "idempotency_key": "revoked"}, access("program:read"))


def test_revision_conflicts_and_one_concurrent_update_wins():
    table = FakeTable()
    store = AuthoredNotesStore(table=table)
    note = store.save_private("author", mutation(0, "create"))
    with pytest.raises(NoteConflict) as missing:
        store.save_private("author", {"note_id": note["note_id"], **mutation(0, "stale")})
    assert missing.value.current_revision == 1

    def update(key):
        try:
            return store.save_private("author", {"note_id": note["note_id"], **mutation(1, key)})
        except NoteConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ("one", "two")))
    assert sum(result is not None for result in results) == 1
    assert table.calls
    assert all(not type(value).__name__.endswith("Serializer") for call in table.calls for value in call.values())


def test_lost_creation_response_replays_without_duplicate_note():
    table = FakeTable()
    store = AuthoredNotesStore(table=table)
    table.lose_next = True
    first = store.save_private("author", mutation(0, "lost response"))
    retry = store.save_private("author", mutation(0, "lost response"))
    assert retry == first
    assert len([key for key in table.items if key[0] == "author" and key[1].startswith("Note#")]) == 1
    with pytest.raises(NoteIdempotencyConflict):
        store.save_private("author", {"text": "changed payload", "expected_revision": 0, "idempotency_key": "lost response"})


def test_competing_shared_revisions_leave_pointer_and_snapshot_consistent():
    table = FakeTable()
    store = AuthoredNotesStore(table=table)
    note = store.save_private("author", mutation(0, "one"))
    note = store.save_private("author", {"note_id": note["note_id"], **mutation(1, "two")})

    def share(revision, key):
        try:
            return store.share("athlete", "author", {"note_id": note["note_id"], "wanted_revision": revision, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": key}, access("program:write"))
        except NoteConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(share, (1, 2), ("share-one", "share-two")))
    winner = next(result for result in results if result)
    listed = store.list_attachments("athlete", {"context_domain": "program"}, access("program:read"))
    assert listed["attachments"] == [winner]


def test_author_partition_and_attachment_identity_prevent_collisions():
    table = FakeTable()
    store = AuthoredNotesStore(table=table)
    first = store.save_private("author-one", mutation(0, "first"))
    second = store.save_private("author-two", {"note_id": "same", **mutation(0, "second")})
    one = store.share("athlete", "author-one", {"note_id": first["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": "one"}, access("program:write"))
    two = store.share("athlete", "author-two", {"note_id": second["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": "two"}, access("program:write"))
    assert one["attachment_id"] != two["attachment_id"]
    with pytest.raises(NoteNotFound):
        store.share("athlete", "author-two", {"note_id": first["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": "wrong-author"}, access("program:write"))


def test_detach_and_share_race_has_one_cas_winner_and_detach_increments_revision():
    table = FakeTable()
    store = AuthoredNotesStore(table=table)
    note = store.save_private("author", mutation(0, "words"))
    initial = store.share("athlete", "author", {"note_id": note["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 0, "idempotency_key": "initial"}, access("program:write"))

    def run_share():
        try:
            return store.share("athlete", "author", {"note_id": note["note_id"], "wanted_revision": 1, "context_domain": "program", "expected_attachment_revision": 1, "idempotency_key": "race-share"}, access("program:write"))
        except NoteConflict:
            return None

    def run_detach():
        try:
            return store.detach("athlete", {"attachment_id": initial["attachment_id"], "expected_attachment_revision": 1, "idempotency_key": "race-detach"}, access("settings:write", is_self=True, own_athlete_pk="athlete"))
        except NoteConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        share_result, detach_result = pool.map(lambda function: function(), (run_share, run_detach))
    assert bool(share_result) ^ bool(detach_result)
    if detach_result:
        assert detach_result["revision"] == 2


def test_transaction_wire_serializes_raw_values_without_type_serializer():
    resource = boto3.resource("dynamodb", region_name="ca-central-1", aws_access_key_id="test", aws_secret_access_key="test", endpoint_url="http://127.0.0.1:1")
    table = resource.Table("if-health")
    captured = {}

    def capture(params, **_kwargs):
        captured.update(json.loads(params["body"]))
        raise RuntimeError("captured")

    table.meta.client.meta.events.register("before-call.dynamodb.TransactWriteItems", capture)
    with pytest.raises(RuntimeError, match="captured"):
        AuthoredNotesStore(table=table)._transaction([{"Put": {"TableName": "if-health", "Item": {"pk": "author", "ratio": 1.25}}}])
    assert captured["TransactItems"][0]["Put"]["Item"]["ratio"] == {"N": "1.25"}
