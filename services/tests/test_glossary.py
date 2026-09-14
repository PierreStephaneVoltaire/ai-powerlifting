import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lambda/layers/pl-glossary/python"))
sys.path.insert(0, str(ROOT))

from services.contract import load_operations
from services.dispatch import dispatch


def test_glossary_contracts_have_real_shapes_and_required_mutations():
    operations = load_operations("glossary")
    assert all(operation.result_schema for operation in operations.values())
    assert operations["exercise_get_glossary"].result_schema["required"] == [
        "pk", "sk", "exercises", "updated_at"
    ]
    for name in ("glossary_add", "glossary_update", "exercise_upsert", "exercise_set_e1rm"):
        with pytest.raises(Exception):
            operations[name].validate_input({})


def test_dispatch_uses_handler_result_shapes_with_fake_store(monkeypatch):
    core = importlib.import_module("lambda.pod_glossary.handlers.exercise_search.core")

    class FakeStore:
        async def search_exercises(self, query):
            return [{"id": "bench", "name": "Bench Press"}]

    monkeypatch.setattr(core, "_get_glossary_store", lambda: FakeStore())
    result = dispatch(load_operations("glossary")["exercise_search"], {"query": "bench"})
    assert result == {"query": "bench", "exercises": [{"id": "bench", "name": "Bench Press"}]}


def test_upsert_merges_existing_metadata_before_handler_write(monkeypatch):
    core = importlib.import_module("lambda.pod_glossary.handlers.exercise_upsert.core")

    class FakeStore:
        def __init__(self):
            self.saved = None

        async def get_exercise_by_id(self, exercise_id):
            return {
                "id": exercise_id,
                "name": "Bench Press",
                "archived": True,
                "e1rm_estimate": {"value_kg": 100},
                "fatigue_profile": {"axial": 2},
                "primary_muscles": ["chest"],
            }

        async def upsert_exercise(self, exercise):
            self.saved = exercise
            return exercise["id"]

    store = FakeStore()
    monkeypatch.setattr(core, "_get_glossary_store", lambda: store)
    result = dispatch(
        load_operations("glossary")["exercise_upsert"],
        {"exercise": {"id": "bench", "name": "Updated Bench"}},
    )
    assert result == {"status": "upserted", "id": "bench"}
    assert store.saved["archived"] is True
    assert store.saved["e1rm_estimate"]["value_kg"] == 100
    assert store.saved["fatigue_profile"]["axial"] == 2
