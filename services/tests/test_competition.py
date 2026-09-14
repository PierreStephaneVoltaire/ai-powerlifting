import importlib

import pytest

from services.contract import load_operations
from services.dispatch import dispatch


class FakeProgramStore:
    pk = "operator"

    def __init__(self):
        self.program = {"competitions": []}

    async def get_program(self):
        return self.program

    async def _write_new_version(self, program, minor=True):
        self.program = program


def test_legacy_competition_round_trip_through_dispatch(monkeypatch):
    store = FakeProgramStore()
    modules = [
        "health_create_competition",
        "health_get_competition",
        "health_update_competition",
        "health_delete_competition",
    ]
    for name in modules:
        module = importlib.import_module(f"lambda.pod_competition.handlers.{name}.core")
        monkeypatch.setattr(module, "_get_store", lambda: store)

    operations = load_operations("competition")
    created = dispatch(operations["health_create_competition"], {"pk": "athlete-1", "competition": {"name": "Meet", "date": "2026-10-01", "federation": "IPF"}})
    assert created["date"] == "2026-10-01"
    updated = dispatch(operations["health_update_competition"], {"pk": "athlete-1", "date": "2026-10-01", "patch": {"status": "completed"}})
    assert updated["status"] == "completed"
    loaded = dispatch(operations["health_get_competition"], {"pk": "athlete-1", "date": "2026-10-01"})
    assert loaded["name"] == "Meet"
    assert dispatch(operations["health_delete_competition"], {"pk": "athlete-1", "date": "2026-10-01"}) == {"deleted": "2026-10-01"}


def test_attempt_calculation_is_validated_and_structured(monkeypatch):
    module = importlib.import_module("lambda.pod_competition.handlers.calculate_attempts.core")
    store = FakeProgramStore()
    store.program = {"operator_prefs": {"attempt_jumps": {"squat": {"j1": 20, "j2": 20}}}, "current_maxes": {"squat": 180}}
    monkeypatch.setattr(module, "_get_store", lambda: store)
    operation = load_operations("competition")["calculate_attempts"]
    result = dispatch(operation, {"pk": "athlete-1", "lift": "squat", "opener_kg": 160})
    assert result["attempt_1_kg"] == 160
    assert result["attempt_2_kg"] == 180
    assert result["warnings"] == ["Attempt 3 (200.0kg) exceeds current max of 180kg — confirm this is a target PR."]
    with pytest.raises(Exception):
        dispatch(operation, {"pk": "athlete-1", "lift": "snatch", "opener_kg": 100})


def test_user_competitions_use_a_partition_query(monkeypatch):
    module = importlib.import_module("lambda.pod_competition.handlers.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [{"pk": "athlete-1", "sk": "COMP#meet", "name": "Meet"}]}

        def scan(self, **_kwargs):
            raise AssertionError("user competition list must not scan the table")

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    assert module.list_competitions({"pk": "athlete-1"}) == [{"name": "Meet"}]
