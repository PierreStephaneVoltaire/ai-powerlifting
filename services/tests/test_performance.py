import asyncio
import importlib
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.contract import load_operations
from services.dispatch import dispatch


class FakeProgramStore:
    def __init__(self):
        self.program = {"current_maxes": {"squat": 180, "bench": 120}}

    async def get_program(self):
        return self.program

    async def mutate_source(self, operation, payload, expected_revision, idempotency_key, mutate):
        assert expected_revision == 0 and idempotency_key == "maxes-edit"
        return mutate(self.program) | {"revision": 1}


def test_performance_contract_requires_real_mutation_payloads():
    operations = load_operations("performance")
    with pytest.raises(Exception):
        operations["health_update_current_maxes"].validate_input({})
    with pytest.raises(Exception):
        operations["max_target_update"].validate_input({"squat_kg": 180})
    operations["max_history_add"].validate_input({"entry": {"date": "2026-09-13", "squat_kg": 180}, "expected_revision": 0, "idempotency_key": "history"})


def test_target_max_update_returns_committed_target_record(monkeypatch):
    max_core = importlib.import_module("lambda.pod_maxes.handlers.max_target_update.core")

    class FakeStore:
        def __init__(self, *_args):
            pass

        async def update_meta_fields(self, updates, expected_revision, idempotency_key):
            assert expected_revision == 4 and idempotency_key == "target-edit"
            return {"success": True, "meta": updates, "revision": 5, "sk": "program#v002", "updated_at": "2026-09-15T10:00:00+00:00"}

    monkeypatch.setitem(sys.modules, "program_store", SimpleNamespace(ProgramStore=FakeStore))
    result = asyncio.run(max_core.max_target_update({"pk": "athlete-1", "version": "v002", "squat_kg": 190, "bench_kg": 125, "deadlift_kg": 230, "expected_revision": 4, "idempotency_key": "target-edit"}))
    load_operations("performance")["max_target_update"].validate_result(result)
    assert result == {"version": "v002", "sk": "program#v002", "squat_kg": 190, "bench_kg": 125, "deadlift_kg": 230, "total_kg": 545, "updated_at": "2026-09-15T10:00:00+00:00", "revision": 5}


def test_program_store_replay_backfills_legacy_commit_metadata():
    from program_store import ProgramStore
    import hashlib
    import json

    key = "target-edit"
    payload = {"updates": {"target_squat_kg": 190}}
    program_sk = "program#v020"
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()

    class Table:
        def get_item(self, **kwargs):
            return {"Item": {"operation": "meta_update", "payload_hash": payload_hash, "result": {"success": True, "meta": payload["updates"], "revision": 1}, "created_at": "2026-09-15T10:00:00+00:00"}}

    store = ProgramStore.__new__(ProgramStore)
    store._pk = "athlete-1"
    store._table = Table()
    store._table_name = "if-health"
    replay = store._source_replay_sync(program_sk, "meta_update", payload, key)
    assert replay["sk"] == program_sk
    assert replay["updated_at"] == "2026-09-15T10:00:00+00:00"


def test_current_maxes_dispatch_uses_fake_store_and_preserves_omitted_lifts(monkeypatch):
    store = FakeProgramStore()
    get_core = importlib.import_module("lambda.pod_maxes.handlers.health_get_current_maxes.core")
    update_core = importlib.import_module("lambda.pod_maxes.handlers.health_update_current_maxes.core")
    monkeypatch.setattr(get_core, "_get_store", lambda: store)
    monkeypatch.setattr(update_core, "_get_store", lambda: store)
    operations = load_operations("performance")

    assert dispatch(operations["health_get_current_maxes"], {"pk": "athlete-1"}) == {"squat": 180, "bench": 120}
    assert dispatch(operations["health_update_current_maxes"], {"pk": "athlete-1", "deadlift_kg": 220, "expected_revision": 0, "idempotency_key": "maxes-edit"}) == {"squat": 180, "bench": 120, "deadlift": 220, "revision": 1}


def test_history_add_computes_total_and_get_filters_window(monkeypatch):
    add_core = importlib.import_module("lambda.pod_maxes.handlers.max_history_add.core")
    get_core = importlib.import_module("lambda.pod_maxes.handlers.max_history_get.core")

    class FakeTable:
        items = {}
        name = "if-health"
        def __init__(self):
            self.meta = type("Meta", (), {"client": self})()

        def get_item(self, **kwargs):
            item = self.items.get((kwargs["Key"]["pk"], kwargs["Key"]["sk"]))
            return {"Item": item} if item else {}

        def transact_write_items(self, TransactItems):
            update = TransactItems[0]["Update"]
            values = update["ExpressionAttributeValues"]
            item = {"pk": update["Key"]["pk"], "sk": update["Key"]["sk"], "entries": values[":entries"], "version": values[":version"], "revision": values[":revision"], "updated_at": values[":updated_at"]}
            self.items[(item["pk"], item["sk"])] = item
            marker = TransactItems[1]["Put"]["Item"]
            self.marker = marker
            self.items[(marker["pk"], marker["sk"])] = marker

    table = FakeTable()
    monkeypatch.setattr(add_core, "_get_table", lambda: table)
    monkeypatch.setattr(get_core, "_get_table", lambda: table)
    monkeypatch.setattr(get_core, 'load_entries', lambda _pk: [])

    asyncio.run(add_core.max_history_add({"pk": "athlete-1", "date": "2026-08-01", "squat_kg": 180, "bench_kg": 120, "expected_revision": 0, "idempotency_key": "first"}))
    asyncio.run(add_core.max_history_add({"pk": "athlete-1", "date": "2026-09-01", "deadlift_kg": 220, "expected_revision": 1, "idempotency_key": "second"}))
    result = asyncio.run(get_core.max_history_get({"pk": "athlete-1", "start_date": "2026-09-01", "end_date": "2026-09-30"}))
    assert result["entries"][0]["date"] == "2026-09-01"
    assert result["revision"] == 2


def test_history_get_scopes_derived_and_tied_competitions(monkeypatch):
    get_core = importlib.import_module("lambda.pod_maxes.handlers.max_history_get.core")
    legacy = {'entry_id': 'competition#meet-a', 'date': '2026-08-01', 'squat_kg': 180, 'bodyweight_kg': 82}
    manual = {'date': '2026-09-15', 'squat_kg': 175, 'total_kg': 175}
    class Table:
        def get_item(self, **kwargs):
            return {'Item': {'pk': 'athlete-1', 'sk': 'max_history#current', 'entries': [legacy, manual]}}
    monkeypatch.setattr(get_core, "_get_table", lambda: Table())
    monkeypatch.setattr(get_core, "load_entries", lambda _pk: [
        {'master_id': 'meet-a', 'user_status': 'completed', 'start_date': '2026-09-01', 'body_weight_kg': 83, 'results': {'squat_kg': 190}},
        {'master_id': 'meet-b', 'user_status': 'completed', 'start_date': '2026-10-01', 'body_weight_kg': 84, 'results': {'squat_kg': 200}},
    ])
    access = {'permissions': ['performance:read'], 'competition_scope': {'read': ['COMP#meet-a']}}
    result = asyncio.run(get_core.max_history_get({'pk': 'athlete-1', '_access': access, 'start_date': '2026-08-01', 'end_date': '2026-09-30'}))
    assert [entry.get('entry_id') for entry in result['entries']] == [None, 'competition#meet-a']
    assert result['entries'][1]['bodyweight_kg'] == 83


def test_handlers_return_json_for_decimal_results():
    handler = importlib.import_module("lambda.pod_maxes.handlers.health_update_current_maxes.handler")
    assert handler._json_default(Decimal("12.5")) == 12.5


def test_unset_targets_are_valid_and_invalid_history_is_rejected():
    operations = load_operations("performance")
    operations["max_target_get"].validate_result({"version": "v001", "sk": "program#v001", "squat_kg": None, "bench_kg": None, "deadlift_kg": None, "total_kg": None})
    for payload in ({"entry": {}}, {"entry": {"date": "bad", "squat_kg": 100}, "expected_revision": 0, "idempotency_key": "x"}, {"date": "2026-09-13", "bench_kg": -1, "expected_revision": 0, "idempotency_key": "x"}):
        with pytest.raises(Exception):
            operations["max_history_add"].validate_input(payload)
