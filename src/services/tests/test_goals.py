import importlib

import pytest

from services.contract import load_operations
from services.dispatch import dispatch


class FakeGoalsStore:
    def __init__(self):
        self.goals = []

    async def list_goals(self, pk):
        return self.goals

    async def replace_goals(self, pk, goals):
        self.goals = [{"id": "goal-1", "title": goal["title"], "goal_type": "custom", "priority": "optional", "target_total_kg": 200.5} for goal in goals]


def test_goals_dispatch_returns_domain_shapes_and_replaces_empty_array(monkeypatch):
    store = FakeGoalsStore()
    list_core = importlib.import_module("services.handlers.goals.goals_list.core")
    replace_core = importlib.import_module("services.handlers.goals.goals_replace.core")
    monkeypatch.setattr(list_core, "_get_store", lambda: store)
    monkeypatch.setattr(replace_core, "_get_store", lambda: store)
    operations = load_operations("goals")

    dispatch(operations["goals_replace"], {"pk": "athlete-1", "goals": [{"title": "Reach total"}]})
    listed = dispatch(operations["goals_list"], {"pk": "athlete-1"})
    assert listed[0]["id"] == "goal-1"
    assert listed[0]["target_total_kg"] == 200.5
    assert dispatch(operations["goals_replace"], {"pk": "athlete-1", "goals": []}) == {"success": True}
    assert dispatch(operations["goals_list"], {"pk": "athlete-1"}) == []


def test_goals_replace_requires_explicit_payload():
    with pytest.raises(Exception):
        load_operations("goals")["goals_replace"].validate_input({})
