import asyncio
import copy
import importlib

import pytest
from botocore.exceptions import ClientError

core = importlib.import_module("services.handlers.maxes.max_history_add.core")


class Table:
    name = "if-health"

    def __init__(self, failure=None):
        self.items = {}
        self.meta = type("Meta", (), {"client": self})()
        self.failure = failure

    def get_item(self, Key, **kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item else {}

    def transact_write_items(self, TransactItems):
        if self.failure:
            error, self.failure = self.failure, None
            if error.__class__.__name__ == "TimeoutError":
                self._apply(TransactItems)
            raise error
        self._apply(TransactItems)

    def _apply(self, operations):
        for operation in operations:
            if "Update" in operation:
                item = operation["Update"]
                key = (item["Key"]["pk"], item["Key"]["sk"])
                values = item["ExpressionAttributeValues"]
                self.items[key] = {"pk": key[0], "sk": key[1], "entries": values[":entries"], "version": values[":version"], "revision": values[":revision"]}
            else:
                item = operation["Put"]["Item"]
                self.items[(item["pk"], item["sk"])] = item


def args(key="one", revision=0, squat=180, person="person-a"):
    return {"pk": "athlete", "_person_pk": person, "version": "current", "expected_revision": revision, "idempotency_key": key, "entry": {"date": "2026-09-14", "squat_kg": squat, "_access": "forged"}}


def test_max_history_lost_reply_same_key_replays_without_duplicate(monkeypatch):
    table = Table(TimeoutError("response lost"))
    monkeypatch.setattr(core, "_get_table", lambda: table)
    first = asyncio.run(core.max_history_add(args()))
    result = asyncio.run(core.max_history_add(args()))
    assert first["revision"] == result["revision"] == 1
    assert len(result["entries"]) == 1
    assert result["revision"] == 1
    assert "_access" not in result["entries"][0]


def test_max_history_transaction_failure_raises_real_revision_conflict(monkeypatch):
    table = Table(ClientError({"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems"))
    monkeypatch.setattr(core, "_get_table", lambda: table)
    with pytest.raises(Exception) as raised:
        asyncio.run(core.max_history_add(args()))
    assert raised.value.__class__.__name__ == "ProgramRevisionConflictError"


def test_max_history_concurrent_different_key_conflicts_without_duplicate(monkeypatch):
    table = Table()
    monkeypatch.setattr(core, "_get_table", lambda: table)
    asyncio.run(core.max_history_add(args("one")))
    with pytest.raises(Exception) as raised:
        asyncio.run(core.max_history_add(args("two")))
    assert raised.value.__class__.__name__ == "ProgramRevisionConflictError"
    assert len(table.items[("athlete", "max_history#current")]["entries"]) == 1


def test_max_history_replay_is_bound_to_verified_person(monkeypatch):
    table = Table()
    monkeypatch.setattr(core, "_get_table", lambda: table)
    first = asyncio.run(core.max_history_add(args("shared", person="person-a")))
    second = asyncio.run(core.max_history_add(args("shared", revision=1, person="person-b", squat=190)))
    replay = asyncio.run(core.max_history_add(args("shared", person="person-a")))
    assert first["revision"] == replay["revision"] == 1
    assert second["revision"] == 2
    assert len(second["entries"]) == 2
    assert len({entry["id"] for entry in second["entries"]}) == 2
    with pytest.raises(ValueError, match="different payload"):
        asyncio.run(core.max_history_add(args("shared", person="person-a", squat=191)))
    stored = table.items[("athlete", "max_history#current")]["entries"][0]
    assert "_person_pk" not in stored and "_access" not in stored
