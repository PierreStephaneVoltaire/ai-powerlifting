import asyncio
import copy
import importlib

core = importlib.import_module("services.handlers.maxes.max_history_add.core")


class Table:
    name = "if-health"

    def __init__(self):
        self.items = {}
        self.puts = 0

    def get_item(self, Key, **kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, Item, **kwargs):
        assert "ConditionExpression" not in kwargs
        self.items[(Item["pk"], Item["sk"])] = copy.deepcopy(Item)
        self.puts += 1


def args(key="one", squat=180, person="person-a", **extra):
    return {"pk": "athlete", "_person_pk": person, "version": "current", "idempotency_key": key, "entry": {"date": "2026-09-14", "squat_kg": squat, "_access": "forged"}, **extra}


def test_max_history_add_is_a_plain_write_without_revision(monkeypatch):
    table = Table()
    monkeypatch.setattr(core, "_get_table", lambda: table)
    result = asyncio.run(core.max_history_add(args()))
    stored = table.items[("athlete", "max_history#current")]
    assert table.puts == 1
    assert "revision" not in result and "revision" not in stored
    assert [entry["squat_kg"] for entry in stored["entries"]] == [180]
    assert set(table.items) == {("athlete", "max_history#current")}


def test_max_history_stale_revision_does_not_block_a_second_entry(monkeypatch):
    table = Table()
    monkeypatch.setattr(core, "_get_table", lambda: table)
    asyncio.run(core.max_history_add(args("one")))
    second = asyncio.run(core.max_history_add(args("two", squat=190, expected_revision=0)))
    assert sorted(entry["squat_kg"] for entry in second["entries"]) == [180, 190]
    assert len({entry["id"] for entry in second["entries"]}) == 2


def test_max_history_resaving_an_entry_replaces_it(monkeypatch):
    table = Table()
    monkeypatch.setattr(core, "_get_table", lambda: table)
    asyncio.run(core.max_history_add(args("shared")))
    resaved = asyncio.run(core.max_history_add(args("shared", squat=185)))
    assert [entry["squat_kg"] for entry in resaved["entries"]] == [185]


def test_max_history_never_stores_internal_fields(monkeypatch):
    table = Table()
    monkeypatch.setattr(core, "_get_table", lambda: table)
    asyncio.run(core.max_history_add(args()))
    stored = table.items[("athlete", "max_history#current")]["entries"][0]
    assert "_person_pk" not in stored and "_access" not in stored
