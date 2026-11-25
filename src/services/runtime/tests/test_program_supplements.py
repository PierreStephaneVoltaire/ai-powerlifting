import copy

import pytest

from services.runtime.program_store import ProgramStore


class Table:
    def __init__(self, items=None, events=None, fail_put=False, name="health"):
        self.items = { (item["pk"], item["sk"]): copy.deepcopy(item) for item in (items or []) }
        self.events = events if events is not None else []
        self.fail_put = fail_put
        self.name = name

    def get_item(self, Key, **kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item is not None else {}

    def put_item(self, Item):
        self.events.append((self.name, Item["sk"]))
        if self.fail_put:
            raise RuntimeError("write failed")
        self.items[(Item["pk"], Item["sk"])] = copy.deepcopy(Item)

    def update_item(self, Key, **kwargs):
        self.events.append((self.name, "pointer"))
        values = kwargs["ExpressionAttributeValues"]
        self.items[(Key["pk"], Key["sk"])].update(current_block_id=values[":block"], updated_at=values[":now"])


def store(health, supplements):
    instance = ProgramStore("health", pk="athlete")
    instance._table = health
    instance._supplements_table = supplements
    return instance


def test_supplement_row_is_authoritative_even_when_attributes_are_empty():
    program = {"supplements": [{"name": "legacy"}], "supplement_phases": [{"phase": 1}]}
    instance = store(Table(), Table([{"pk": "athlete", "sk": "program#v001", "supplements": []}]))

    assert instance._hydrate_supplements_sync(program, "program#v001") is True
    assert program == {"supplements": []}


def test_missing_supplement_row_keeps_legacy_fields():
    program = {"supplements": [{"name": "legacy"}]}
    instance = store(Table(), Table())

    assert instance._hydrate_supplements_sync(program, "program#v001") is False
    assert program["supplements"] == [{"name": "legacy"}]


def test_source_commit_keeps_newer_supplement_row_and_strips_health_fields():
    events = []
    health = Table([{"pk": "athlete", "sk": "program#v001", "notes": "before"}], events)
    supplements = Table([{"pk": "athlete", "sk": "program#v001", "supplements": [{"name": "new"}], "supplement_phases": []}], events, name="supplements")
    instance = store(health, supplements)
    snapshot_program = {"notes": "before", "supplements": [{"name": "old"}], "supplement_phases": []}
    program = {**snapshot_program, "notes": "after"}

    instance._commit_source_sync((snapshot_program, {}, "program#v001", True), program, "edit", {}, {})

    assert supplements.items[("athlete", "program#v001")]["supplements"] == [{"name": "new"}]
    assert "supplements" not in health.items[("athlete", "program#v001")]
    assert events == [("health", "program#v001")]


def test_source_commit_can_delete_last_field_without_resurrecting_legacy_values():
    health = Table()
    supplements = Table([{"pk": "athlete", "sk": "program#v001", "supplements": [{"name": "old"}]}], name="supplements")
    instance = store(health, supplements)
    snapshot_program = {"supplements": [{"name": "old"}]}

    instance._commit_source_sync((snapshot_program, {}, "program#v001", True), {}, "edit", {}, {})

    assert supplements.items[("athlete", "program#v001")] == {"pk": "athlete", "sk": "program#v001"}
    assert "supplements" not in health.items[("athlete", "program#v001")]


def test_source_commit_persists_legacy_data_before_health_and_stops_on_failure():
    events = []
    health = Table([{"pk": "athlete", "sk": "program#v001", "supplements": [{"name": "legacy"}]}], events)
    supplements = Table(events=events, fail_put=True, name="supplements")
    instance = store(health, supplements)
    program = {"supplements": [{"name": "legacy"}]}

    with pytest.raises(RuntimeError, match="write failed"):
        instance._commit_source_sync((program, {}, "program#v001", True), program, "edit", {}, {})

    assert events == [("supplements", "program#v001")]
    assert "supplements" in health.items[("athlete", "program#v001")]


def test_save_in_place_writes_supplements_before_health_item(monkeypatch):
    events = []
    health = Table([{"pk": "athlete", "sk": ProgramStore.POINTER_SK, "ref_sk": "program#v001"}], events)
    supplements = Table(events=events, name="supplements")
    instance = store(health, supplements)

    class Sessions:
        def replace_program_sessions_sync(self, *args):
            events.append(("sessions", ""))

    monkeypatch.setattr(instance, "_get_session_store", lambda: Sessions())
    written = instance._save_in_place_sync({
        "meta": {},
        "phases": [],
        "sessions": [],
        "supplements": [{"name": "creatine"}],
        "supplement_phases": [],
    })

    health_sk = "program#v001"
    assert events[0] == ("supplements", health_sk)
    assert events[1] == ("health", health_sk)
    assert events[2] == ("health", "pointer")
    assert "supplements" not in health.items[("athlete", health_sk)]
    assert supplements.items[("athlete", health_sk)]["supplements"] == [{"name": "creatine"}]
    assert written["supplements"] == [{"name": "creatine"}]


def test_save_in_place_supplement_failure_does_not_write_health_item(monkeypatch):
    events = []
    health = Table([{"pk": "athlete", "sk": ProgramStore.POINTER_SK, "ref_sk": "program#v001"}], events)
    supplements = Table(events=events, fail_put=True, name="supplements")
    instance = store(health, supplements)

    with pytest.raises(RuntimeError, match="write failed"):
        instance._save_in_place_sync({"meta": {}, "sessions": [], "supplements": [{"name": "creatine"}]})

    assert len(events) == 1
    assert events[0][0] == "supplements"
    assert events[0][1] == "program#v001"
    assert ("athlete", "program#v001") not in health.items
