import sys
import json
import importlib
import asyncio
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lambda/layers/pl-sessions/python"))
sys.path.insert(0, str(ROOT))

from services.contract import load_operations
from session_store import SessionStore
from session_tool_helpers import resolve_context


def test_session_operation_results_describe_handler_shapes():
    operations = load_operations("sessions")

    assert all(operation.result_schema for operation in operations.values())
    assert operations["session_list_full"].result_schema["type"] == "array"
    assert operations["health_get_sessions_range"].result_schema["type"] == "array"
    assert operations["session_delete"].result_schema["required"] == ["deleted"]
    assert operations["session_replace_all"].result_schema["required"] == ["success"]
    operations["session_list"].validate_result({"sessions": [], "count": 0, "total": 0})
    with pytest.raises(Exception):
        operations["session_replace_all"].validate_input({})
    with pytest.raises(Exception):
        operations["session_create"].validate_input({})
    with pytest.raises(Exception):
        operations["session_patch"].validate_input({"date": "2026-09-13", "patch": {}})


def test_index_is_ordinal_within_date():
    store = SessionStore.__new__(SessionStore)
    store._query_items_sync = lambda _program_sk: [
        {"date": "2026-09-12", "sk": "old"},
        {"date": "2026-09-13", "sk": "first"},
        {"date": "2026-09-13", "sk": "second"},
    ]

    assert store._find_item_sync("program#v001", "2026-09-13", 0)["sk"] == "first"
    assert store._find_item_sync("program#v001", "2026-09-13", 1)["sk"] == "second"
    with pytest.raises(ValueError, match="Session at index 2 not found"):
        store._find_item_sync("program#v001", "2026-09-13", 2)


def test_real_list_handler_result_matches_contract(monkeypatch):
    session_list_full = importlib.import_module("lambda.pod_sessions.handlers.session_list_full.handler")
    session_core = importlib.import_module("lambda.pod_sessions.handlers.session_list_full.core")

    class FakeStore:
        async def list_sessions(self, program_sk, phases):
            return [{"date": "2026-09-13", "week_number": 1, "phase": {}}]

    monkeypatch.setattr(session_core, "get_store", lambda _args: FakeStore())
    monkeypatch.setattr(session_core, "resolve_context", lambda _store, _program_sk: _context())

    async def _context():
        return "program#v001", []

    response = session_list_full.handler({}, None)
    result = json.loads(response["body"])
    load_operations("sessions")["session_list_full"].validate_result(result)


def test_identity_fields_are_rejected_before_store_mutation(monkeypatch):
    core = importlib.import_module("lambda.pod_sessions.handlers.session_patch.core")

    class FakeStore:
        async def patch_session(self, *args):
            raise AssertionError("identity patch reached storage")

    monkeypatch.setattr(core, "get_store", lambda _args: FakeStore())
    monkeypatch.setattr(core, "resolve_context", lambda _store, _program_sk: _context())

    async def _context():
        return "program#v001", []

    with pytest.raises(ValueError, match="identity"):
        asyncio.run(core.session_patch({"date": "2026-09-13", "index": 0, "patch": {"id": "new"}}))


def test_full_replace_accepts_the_persisted_session_id(monkeypatch):
    core = importlib.import_module("lambda.pod_sessions.handlers.session_replace.core")

    class FakeStore:
        async def patch_session(self, *args):
            return args

    monkeypatch.setattr(core, "get_store", lambda _args: FakeStore())
    monkeypatch.setattr(core, "resolve_context", lambda _store, _program_sk: _context())

    async def _context():
        return "program#v001", []

    result = asyncio.run(core.session_replace({"date": "2026-09-13", "index": 0, "session": {"id": "persisted-id"}}))
    assert result[-1] == 0
    assert result[2] == {"id": "persisted-id"}


def test_store_rejects_a_replacement_with_a_different_id():
    store = SessionStore.__new__(SessionStore)
    store._find_item_sync = lambda *_args: {"session_id": "persisted-id"}

    with pytest.raises(ValueError, match="identity"):
        store.patch_session_sync("program#v001", "2026-09-13", {"id": "different-id"}, [], 0)


def test_context_aliases_resolve_current_and_preserve_history():
    class FakeStore:
        async def resolve_program_sk(self):
            return "program#v002"

        async def load_phases(self, program_sk):
            return [program_sk]

    store = FakeStore()
    for alias in (None, "current", "program#current"):
        assert asyncio.run(resolve_context(store, alias)) == ("program#v002", ["program#v002"])
    assert asyncio.run(resolve_context(store, "program#v001")) == ("program#v001", ["program#v001"])


def test_session_list_resolves_current_aliases_against_pointer(monkeypatch):
    core = importlib.import_module("lambda.pod_sessions.handlers.session_list.core")

    class FakeSourceTable:
        def get_item(self, **kwargs):
            assert kwargs["Key"] == {"pk": "operator", "sk": "program#current"}
            return {"Item": {"ref_sk": "program#v002"}}

    class FakeStore:
        def __init__(self, **kwargs):
            self.source_table = FakeSourceTable()

        def resolve_program_sk_sync(self):
            return self.source_table.get_item(Key={"pk": "operator", "sk": "program#current"})["Item"]["ref_sk"]

    class FakeTable:
        def query(self, **kwargs):
            return {
                "Items": [
                    {"pk": "operator", "sk": "session#1", "program_sk": "program#v002", "date": "2026-09-13"}
                ]
            }

    monkeypatch.setattr(core, "_get_table", lambda: FakeTable())
    monkeypatch.setattr("session_store.SessionStore", FakeStore)

    for alias in (None, "current", "program#current"):
        result = asyncio.run(core.session_list({"pk": "operator", "program_sk": alias, "limit": 1}))
        assert result["total"] == 1
    result = asyncio.run(core.session_list({"pk": "operator", "program_sk": "program#v001", "limit": 1}))
    assert result["total"] == 0
