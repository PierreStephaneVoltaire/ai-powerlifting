import asyncio
import importlib
from decimal import Decimal

import pytest

from services.contract import load_operations
from services.dispatch import dispatch


class FakeProgramStore:
    def __init__(self):
        self.program = {"current_maxes": {"squat": 180, "bench": 120}}

    async def get_program(self):
        return self.program

    async def _write_new_version(self, program, minor=True):
        self.program = program


def test_performance_contract_requires_real_mutation_payloads():
    operations = load_operations("performance")
    with pytest.raises(Exception):
        operations["health_update_current_maxes"].validate_input({})
    with pytest.raises(Exception):
        operations["max_target_update"].validate_input({"squat_kg": 180})
    operations["max_history_add"].validate_input({"entry": {"date": "2026-09-13", "squat_kg": 180}})


def test_current_maxes_dispatch_uses_fake_store_and_preserves_omitted_lifts(monkeypatch):
    store = FakeProgramStore()
    get_core = importlib.import_module("lambda.pod_maxes.handlers.health_get_current_maxes.core")
    update_core = importlib.import_module("lambda.pod_maxes.handlers.health_update_current_maxes.core")
    monkeypatch.setattr(get_core, "_get_store", lambda: store)
    monkeypatch.setattr(update_core, "_get_store", lambda: store)
    operations = load_operations("performance")

    assert dispatch(operations["health_get_current_maxes"], {"pk": "athlete-1"}) == {"squat": 180, "bench": 120}
    assert dispatch(operations["health_update_current_maxes"], {"pk": "athlete-1", "deadlift_kg": 220}) == {"squat": 180, "bench": 120, "deadlift": 220}


def test_history_add_computes_total_and_get_filters_window(monkeypatch):
    add_core = importlib.import_module("lambda.pod_maxes.handlers.max_history_add.core")
    get_core = importlib.import_module("lambda.pod_maxes.handlers.max_history_get.core")

    class FakeTable:
        item = None

        def get_item(self, **kwargs):
            return {"Item": self.item} if self.item else {}

        def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues, ReturnValues):
            assert "list_append(if_not_exists" in UpdateExpression
            values = ExpressionAttributeValues
            self.item = {**Key, "entries": (self.item or {}).get("entries", []) + values[":entry"], "version": values[":version"], "updated_at": values[":now"]}
            return {"Attributes": self.item}

    table = FakeTable()
    monkeypatch.setattr(add_core, "_get_table", lambda: table)
    monkeypatch.setattr(get_core, "_get_table", lambda: table)

    asyncio.run(add_core.max_history_add({"pk": "athlete-1", "date": "2026-08-01", "squat_kg": 180, "bench_kg": 120}))
    asyncio.run(add_core.max_history_add({"pk": "athlete-1", "date": "2026-09-01", "deadlift_kg": 220}))
    result = asyncio.run(get_core.max_history_get({"pk": "athlete-1", "start_date": "2026-09-01", "end_date": "2026-09-30"}))
    assert result["entries"] == [{"date": "2026-09-01", "deadlift_kg": 220, "total_kg": 220}]


def test_handlers_return_json_for_decimal_results():
    handler = importlib.import_module("lambda.pod_maxes.handlers.health_update_current_maxes.handler")
    assert handler._json_default(Decimal("12.5")) == 12.5


def test_unset_targets_are_valid_and_invalid_history_is_rejected():
    operations = load_operations("performance")
    operations["max_target_get"].validate_result({"version": "v001", "sk": "program#v001", "squat_kg": None, "bench_kg": None, "deadlift_kg": None, "total_kg": None})
    for payload in ({"entry": {}}, {"entry": {"date": "bad", "squat_kg": 100}}, {"date": "2026-09-13", "bench_kg": -1}):
        with pytest.raises(Exception):
            operations["max_history_add"].validate_input(payload)
