import json
import importlib
import asyncio
import copy
from types import SimpleNamespace

import pytest


from services.contract import load_operations

from services.lib.session_store import SessionIdentityConflictError, SessionStore
from services.lib.session_tool_helpers import resolve_context


class WireTable:
    def __init__(self, name, items):
        self.name = name
        self.items = {(item["pk"], item["sk"]): copy.deepcopy(item) for item in items}
        self.meta = SimpleNamespace(client=None)
        self.puts = []

    def get_item(self, Key, **_kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item else {}

    def query(self, **_kwargs):
        return {"Items": copy.deepcopy(list(self.items.values()))}

    def put_item(self, Item, **kwargs):
        assert "ConditionExpression" not in kwargs
        self.puts.append(copy.deepcopy(Item))
        self.items[(Item["pk"], Item["sk"])] = copy.deepcopy(Item)

    def delete_item(self, Key, **kwargs):
        assert "ConditionExpression" not in kwargs
        self.items.pop((Key["pk"], Key["sk"]), None)


def test_session_writes_are_plain_puts_to_the_session_table_only(monkeypatch):
    program = {"pk": "athlete", "sk": "program#v001", "meta": {}}
    source = WireTable("if-health", [{"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001"}, program])
    sessions = WireTable("if-sessions", [])
    store = SessionStore("if-sessions", "athlete", source_table_name="if-health")
    store._table = sessions
    store._source_table = source
    monkeypatch.setattr(store, "_invalidate_caches", lambda: None)

    created = store.create_session_sync("program#v001", {"date": "2026-09-14", "week_number": 1, "exercises": [{"sets": 1, "kg": 100.5}]})
    assert created["id"]

    def contains_float(value):
        if isinstance(value, float):
            return True
        if isinstance(value, dict):
            return any(contains_float(child) for child in value.values())
        if isinstance(value, list):
            return any(contains_float(child) for child in value)
        return False

    assert len(sessions.puts) == 1 and not contains_float(sessions.puts[0])
    updated = store.patch_session_sync("program#v001", "2026-09-14", {"session_notes": "logged"})
    assert updated["session_notes"] == "logged"
    stored = next(iter(sessions.items.values()))
    assert stored["session_notes"] == "logged" and "revision" not in stored
    assert source.puts == [] and source.items[("athlete", "program#v001")] == program


def test_session_identity_collisions_are_rejected_before_writes(monkeypatch):
    source = WireTable("if-health", [
        {"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001", "revision": 4},
        {"pk": "athlete", "sk": "program#v001", "meta": {"revision": 4}},
    ])
    sessions = WireTable("if-sessions", [{
        "pk": "athlete", "sk": "session#program#v001#2026-09-14#001#history",
        "session_id": "history", "id": "history", "date": "2026-09-14",
    }])
    store = SessionStore("if-sessions", "athlete", source_table_name="if-health")
    store._table = sessions
    store._source_table = source
    monkeypatch.setattr(store, "_invalidate_caches", lambda: None)

    with pytest.raises(SessionIdentityConflictError, match="already exists"):
        store.create_session_sync(
            "program#v001", {"id": "history", "date": "2026-09-15"},
            expected_revision=4, idempotency_key="duplicate-create",
        )
    assert sessions.puts == []
    with pytest.raises(SessionIdentityConflictError, match="occurs more than once"):
        store.replace_program_sessions_sync(
            "program#v001", [{"id": "new", "date": "2026-09-15"}, {"id": "new", "date": "2026-09-16"}],
            [], bump_program_revision=False,
        )
    assert len(sessions.items) == 1


def test_explicit_lookup_rejects_legacy_ambiguous_identity(monkeypatch):
    source = WireTable("if-health", [
        {"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001", "revision": 4},
        {"pk": "athlete", "sk": "program#v001", "meta": {"revision": 4}},
    ])
    sessions = WireTable("if-sessions", [
        {"pk": "athlete", "sk": "session#program#v001#2026-09-14#001#legacy-a", "session_id": "legacy", "date": "2026-09-14"},
        {"pk": "athlete", "sk": "session#program#v001#2026-09-15#001#legacy-b", "session_id": "legacy", "date": "2026-09-15"},
    ])
    store = SessionStore("if-sessions", "athlete", source_table_name="if-health")
    store._table = sessions
    store._source_table = source

    with pytest.raises(ValueError, match="ambiguous"):
        store._find_item_sync("program#v001", "2026-09-14", session_id="legacy")


def test_training_patch_preserves_stored_media(monkeypatch):
    source = WireTable("if-health", [{"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001"}])
    sessions = WireTable("if-sessions", [{
        "pk": "athlete",
        "sk": "session#program#v001#2026-09-14#001#session-1",
        "session_id": "session-1",
        "id": "session-1",
        "date": "2026-09-14",
        "week_number": 1,
        "exercises": [],
        "videos": [{"video_id": "worker-ready", "thumbnail_status": "ready"}],
    }])
    store = SessionStore("if-sessions", "athlete", source_table_name="if-health")
    store._table = sessions
    store._source_table = source
    monkeypatch.setattr(store, "_invalidate_caches", lambda: None)

    result = store.patch_session_sync("program#v001", "2026-09-14", {"session_notes": "logged", "videos": []})
    assert result["videos"] == [{"video_id": "worker-ready", "thumbnail_status": "ready"}]
    put = sessions.puts[-1]
    assert put["videos"] == [{"video_id": "worker-ready", "thumbnail_status": "ready"}]
    assert "media_revision" not in put and "revision" not in put


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


def test_stable_session_id_wins_when_same_day_order_changes(monkeypatch):
    source = WireTable("if-health", [
        {"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001", "revision": 4},
        {"pk": "athlete", "sk": "program#v001", "meta": {"revision": 4}},
    ])
    sessions = WireTable("if-sessions", [
        {"pk": "athlete", "sk": "session#program#v001#2026-09-13#001#first", "session_id": "first", "id": "first", "date": "2026-09-13", "week_number": 1, "exercises": [], "revision": 1, "same_day_ordinal": 1},
        {"pk": "athlete", "sk": "session#program#v001#2026-09-13#002#second", "session_id": "second", "id": "second", "date": "2026-09-13", "week_number": 1, "exercises": [], "revision": 1, "same_day_ordinal": 2},
    ])
    store = SessionStore("if-sessions", "athlete", source_table_name="if-health")
    store._table = sessions
    store._source_table = source
    monkeypatch.setattr(store, "_invalidate_caches", lambda: None)

    first, second = sessions.items.values()
    first["same_day_ordinal"], second["same_day_ordinal"] = 2, 1
    updated = store.patch_session_sync("program#v001", "2026-09-13", {"session_notes": "intended"}, [], 0, session_id="second")

    assert updated["id"] == "second"
    assert updated["session_notes"] == "intended"


def test_date_only_lookup_rejects_ambiguous_sessions_and_missing_id():
    store = SessionStore.__new__(SessionStore)
    store._query_items_sync = lambda _program_sk: [
        {"date": "2026-09-13", "session_id": "first"},
        {"date": "2026-09-13", "session_id": "second"},
    ]
    with pytest.raises(ValueError, match="choose one by id"):
        store._find_item_sync("program#v001", "2026-09-13")
    with pytest.raises(ValueError, match="no longer exists"):
        store._find_item_sync("program#v001", "2026-09-13", session_id="deleted")


def test_legacy_session_handlers_bind_every_mutation_to_the_stable_id(monkeypatch):
    session_date = "2026-09-13"
    program = {
        "meta": {"revision": 8},
        "phases": [],
        "sessions": [
            {"id": "first", "session_id": "first", "date": session_date, "exercises": [{"name": "first lift"}]},
            {"id": "second", "session_id": "second", "date": session_date, "exercises": [{"name": "second lift"}]},
        ],
    }
    state = {"programs": {"athlete-requested": copy.deepcopy(program), "operator": copy.deepcopy(program)}, "calls": [], "store_pks": []}
    state["programs"]["operator"]["sessions"][1]["exercises"] = [{"name": "default lift"}]

    class FakeProgramStore:
        def __init__(self, pk="operator"):
            self.pk = pk
            self.table = FakeTable()
            state["store_pks"].append(pk)

        async def get_program(self):
            return copy.deepcopy(state["programs"][self.pk])

        def invalidate_cache(self):
            return None

        async def update_session(self, date, patch, expected_revision, idempotency_key, session_id=None):
            state["calls"].append(("update", self.pk, date, patch, expected_revision, idempotency_key, session_id))
            target = next(session for session in state["programs"][self.pk]["sessions"] if session["id"] == session_id)
            target.update(copy.deepcopy(patch))
            return copy.deepcopy(state["programs"][self.pk])

    class FakeTable:
        def get_item(self, Key):
            return {"Item": {"ref_sk": "program#v001"}} if Key["sk"] == "program#current" else {}

    class FakeSessionStore:
        def __init__(self, *args, **kwargs):
            self.pk = kwargs["pk"]
            state["store_pks"].append(self.pk)

        async def patch_session(self, program_sk, date, patch, phases, index, expected_revision, idempotency_key, session_id=None):
            state["calls"].append(("patch", self.pk, program_sk, date, patch, expected_revision, idempotency_key, session_id))
            target = next(session for session in state["programs"][self.pk]["sessions"] if session["id"] == session_id)
            target.update(copy.deepcopy(patch))
            return copy.deepcopy(target)

        async def delete_session(self, program_sk, date, index, expected_revision, idempotency_key, session_id=None):
            state["calls"].append(("delete", self.pk, program_sk, date, index, expected_revision, idempotency_key, session_id))
            return {"deleted": session_id}

        async def get_sessions_range(self, *args):
            return []

    from services.lib import session_store
    monkeypatch.setattr(session_store, "SessionStore", FakeSessionStore)

    health_get = importlib.import_module("services.handlers.sessions.health_get_session.core")
    health_add = importlib.import_module("services.handlers.sessions.health_add_exercise.core")
    health_remove = importlib.import_module("services.handlers.sessions.health_remove_exercise.core")
    health_delete = importlib.import_module("services.handlers.sessions.health_delete_session.core")
    health_reschedule = importlib.import_module("services.handlers.sessions.health_reschedule_session.core")
    health_update = importlib.import_module("services.handlers.sessions.health_update_session.core")
    patch_by_date = importlib.import_module("services.handlers.sessions.session_patch_by_date.core")
    for module in (health_get, health_add, health_remove, health_delete, health_reschedule, health_update):
        monkeypatch.setattr(module, "_store_for", lambda pk: FakeProgramStore(pk or "operator"))
    class FakeContextStore:
        async def patch_session(self, program_sk, date, patch, phases, index, session_id=None, **kwargs):
            state["calls"].append(("patch_by_date", program_sk, date, patch, session_id))
            return copy.deepcopy(state["programs"]["athlete-requested"]["sessions"][1])

    monkeypatch.setattr(patch_by_date, "get_store", lambda _args: FakeContextStore())
    monkeypatch.setattr(patch_by_date, "resolve_context", lambda *_args: _patch_context())

    args = {"pk": "athlete-requested", "date": session_date, "session_id": "second", "expected_revision": 8, "idempotency_key": "stable"}
    selected = asyncio.run(health_get.health_get_session(args))
    assert selected["id"] == "second"
    asyncio.run(patch_by_date.session_patch_by_date({**args, "patch": {"session_notes": "second note"}}))
    added = asyncio.run(health_add.health_add_exercise({**args, "exercise": {"name": "second accessory"}}))
    assert added["exercises"][0]["name"] == "second lift"
    asyncio.run(health_remove.health_remove_exercise({**args, "exercise_index": 0}))
    asyncio.run(health_delete.health_delete_session(args))
    asyncio.run(health_reschedule.health_reschedule_session({**args, "old_date": session_date, "new_date": "2026-09-14"}))
    asyncio.run(health_update.health_update_session({**args, "patch": {"session_notes": "second note"}}))

    assert [call[-1] for call in state["calls"]] == ["second", "second", "second", "second", "second", "second"]
    assert all(pk == "athlete-requested" for pk in state["store_pks"])
    assert state["calls"][0][0] == "patch_by_date"
    assert state["calls"][1][0] == "patch"
    assert state["calls"][2][0] == "patch"
    assert state["calls"][3][0] == "delete"
    assert state["calls"][4][0] == "patch"
    assert state["calls"][5][0] == "update"
    assert state["programs"]["operator"]["sessions"][1]["exercises"] == [{"name": "default lift"}]


async def _patch_context():
    return "program#v001", []


def test_patching_a_deleted_session_reports_it_is_gone(monkeypatch):
    source = WireTable("if-health", [{"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001"}])
    sessions = WireTable("if-sessions", [])
    store = SessionStore("if-sessions", "athlete", source_table_name="if-health")
    store._table = sessions
    store._source_table = source
    monkeypatch.setattr(store, "_invalidate_caches", lambda: None)

    with pytest.raises(ValueError, match="no longer exists"):
        store.patch_session_sync("program#v001", "2026-09-13", {"session_notes": "keep draft"}, session_id="deleted-session")
    assert sessions.puts == []


def test_identity_conflict_code_survives_service_transports(monkeypatch):
    monkeypatch.setenv("PL_DOMAIN", "sessions")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "transport-test")
    services_app = importlib.reload(importlib.import_module("services.app"))
    monkeypatch.setattr(services_app, "authorize_request", lambda *args: _authorized_session_request())
    monkeypatch.setattr(services_app, "authorize", lambda operation, arguments, athlete, person, access: arguments)

    monkeypatch.setattr(services_app, "dispatch", lambda *_args: (_ for _ in ()).throw(SessionIdentityConflictError("deleted-session", 8)))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as http_error:
        asyncio.run(services_app.call("session_patch", {"date": "2026-09-14", "index": 0, "patch": {}, "expected_revision": 7, "idempotency_key": "transport-test"}, "athlete", "person"))
    assert http_error.value.status_code == 409
    assert http_error.value.detail["code"] == "session_identity_conflict"
    from fastapi.testclient import TestClient
    with TestClient(services_app.app) as client:
        response = client.post("/mcp", headers={"X-Internal-Token": "transport-test"}, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "session_patch",
                "arguments": {"date": "2026-09-14", "index": 0, "patch": {}, "expected_revision": 7, "idempotency_key": "mcp-transport-test"},
            },
        })
    mcp_error = json.loads(response.json()["result"]["content"][0]["text"])
    assert mcp_error["error"]["code"] == "session_identity_conflict"


async def _authorized_session_request():
    return {"sub": "person", "athlete": "athlete"}, {}


def test_real_list_handler_result_matches_contract(monkeypatch):
    session_list_full = importlib.import_module("services.handlers.sessions.session_list_full.handler")
    session_core = importlib.import_module("services.handlers.sessions.session_list_full.core")

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
    core = importlib.import_module("services.handlers.sessions.session_patch.core")

    class FakeStore:
        async def patch_session(self, *args):
            raise AssertionError("identity patch reached storage")

    monkeypatch.setattr(core, "get_store", lambda _args: FakeStore())
    monkeypatch.setattr(core, "resolve_context", lambda _store, _program_sk: _context())

    async def _context():
        return "program#v001", []

    with pytest.raises(ValueError, match="identity"):
        asyncio.run(core.session_patch({"date": "2026-09-13", "index": 0, "patch": {"id": "new"}, "expected_revision": 0, "idempotency_key": "identity-patch"}))


def test_full_replace_accepts_the_persisted_session_id(monkeypatch):
    core = importlib.import_module("services.handlers.sessions.session_replace.core")

    class FakeStore:
        async def patch_session(self, *args, **_kwargs):
            return args

    monkeypatch.setattr(core, "get_store", lambda _args: FakeStore())
    monkeypatch.setattr(core, "resolve_context", lambda _store, _program_sk: _context())

    async def _context():
        return "program#v001", []

    result = asyncio.run(core.session_replace({"date": "2026-09-13", "index": 0, "session": {"id": "persisted-id"}, "expected_revision": 0, "idempotency_key": "replace-session"}))
    assert result[-1] == 0
    assert result[2] == {"id": "persisted-id"}


def test_store_rejects_a_replacement_with_a_different_id():
    store = SessionStore.__new__(SessionStore)
    store._find_item_sync = lambda *_args: {"session_id": "persisted-id"}
    store._replay_sync = lambda *_args: None

    with pytest.raises(ValueError, match="identity"):
        store.patch_session_sync("program#v001", "2026-09-13", {"id": "different-id"}, [], 0, 0, "different-id")


def test_session_mutations_require_revision_and_idempotency_envelope():
    operations = load_operations("sessions")
    for name, payload in {
        "session_create": {"session": {}},
        "session_patch": {"date": "2026-09-13", "patch": {}},
        "session_delete": {"date": "2026-09-13"},
        "session_replace": {"date": "2026-09-13", "session": {}},
        "session_reschedule": {"date": "2026-09-13", "new_date": "2026-09-14"},
        "health_add_exercise": {"date": "2026-09-13", "exercise": {}},
        "health_remove_exercise": {"date": "2026-09-13", "exercise_index": 0},
    }.items():
        with pytest.raises(Exception):
            operations[name].validate_input(payload)


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
    core = importlib.import_module("services.handlers.sessions.session_list.core")

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
    monkeypatch.setattr("services.lib.session_store.SessionStore", FakeStore)

    for alias in (None, "current", "program#current"):
        result = asyncio.run(core.session_list({"pk": "operator", "program_sk": alias, "limit": 1}))
        assert result["total"] == 1
    result = asyncio.run(core.session_list({"pk": "operator", "program_sk": "program#v001", "limit": 1}))
    assert result["total"] == 0
