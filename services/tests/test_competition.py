import importlib
import copy
import json
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from services.contract import load_operations
from services.dispatch import dispatch
from services.lib.session_store import SessionIdentityConflictError


def test_competition_program_writers_validate_sessions_before_program_put(monkeypatch):
    class Table:
        def __init__(self):
            self.puts = 0

        def put_item(self, **_kwargs):
            self.puts += 1

    class Store:
        pk = "athlete"

        def __init__(self, table):
            self.table = table

        def invalidate_cache(self):
            pass

    class Sessions:
        def _ensure_unique_session_ids(self, _sessions, _program_sk):
            raise SessionIdentityConflictError("duplicate", 4, "Session identity duplicate occurs more than once")

    table = Table()
    store = Store(table)
    session_module = importlib.import_module("services.lib.session_store")
    monkeypatch.setattr(session_module, "SessionStore", lambda **_kwargs: Sessions())
    for module_name in (
        "services.handlers.competition.health_complete_competition.core",
        "services.handlers.competition.health_snapshot_competition_projection.core",
    ):
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, "_get_table_and_pk", lambda: (table, "athlete", store))
        with pytest.raises(SessionIdentityConflictError):
            module._save_program_version({"sessions": [{"id": "duplicate"}, {"id": "duplicate"}]}, "program#v002")
        assert table.puts == 0


class FakeProgramStore:
    pk = "operator"

    def __init__(self):
        self.program = {"competitions": []}
        self.revision = 0

    async def get_program(self):
        return self.program

    async def _write_new_version(self, program, minor=True):
        self.program = program

    async def mutate_source(self, operation, payload, expected_revision, idempotency_key, mutator):
        if expected_revision != self.revision:
            from services.lib.program_store import ProgramRevisionConflictError
            raise ProgramRevisionConflictError(expected_revision, self.revision, self.program)
        updated = copy.deepcopy(self.program)
        result = mutator(updated)
        self.program = updated
        self.revision += 1
        return {**result, "revision": self.revision}


def test_legacy_competition_round_trip_through_dispatch(monkeypatch):
    store = FakeProgramStore()
    modules = [
        "health_create_competition",
        "health_get_competition",
        "health_update_competition",
        "health_delete_competition",
    ]
    for name in modules:
        module = importlib.import_module(f"services.handlers.competition.{name}.core")
        monkeypatch.setattr(module, "_get_store", lambda: store)

    operations = load_operations("competition")
    created = dispatch(operations["health_create_competition"], {"pk": "athlete-1", "expected_revision": 0, "idempotency_key": "create", "competition": {"name": "Meet", "date": "2026-10-01", "federation": "IPF"}})
    assert created["date"] == "2026-10-01"
    updated = dispatch(operations["health_update_competition"], {"pk": "athlete-1", "date": "2026-10-01", "patch": {"status": "completed"}, "expected_revision": 1, "idempotency_key": "update"})
    assert updated["status"] == "completed"
    loaded = dispatch(operations["health_get_competition"], {"pk": "athlete-1", "date": "2026-10-01"})
    assert loaded["name"] == "Meet"
    assert dispatch(operations["health_delete_competition"], {"pk": "athlete-1", "date": "2026-10-01", "expected_revision": 2, "idempotency_key": "delete"}) == {"deleted": "2026-10-01", "revision": 3}


def test_attempt_calculation_is_validated_and_structured(monkeypatch):
    module = importlib.import_module("services.handlers.competition.calculate_attempts.core")
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
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [{"pk": "athlete-1", "sk": "COMP#meet", "name": "Meet"}]}

        def scan(self, **_kwargs):
            raise AssertionError("user competition list must not scan the table")

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")
    assert module.list_competitions({"pk": "athlete-1"}) == [{"name": "Meet", "revision": 0, "units": "kg"}]


def test_user_competitions_show_directory_and_selected_block_participation(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [
                {"pk": "a", "sk": "COMP#dir", "name": "Directory meet", "user_status": "available", "start_date": "2026-12-01"},
                {"pk": "a", "sk": "COMP#old", "name": "2025 Provincials", "user_status": "completed", "block_id": "block-2025", "start_date": "2025-03-01"},
                {"pk": "a", "sk": "COMP#new", "name": "2026 Nationals", "user_status": "confirmed", "block_id": "block-new", "start_date": "2026-11-01"},
            ]}

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")
    assert [c["name"] for c in module.list_competitions({"pk": "a"})] == ["2026 Nationals", "Directory meet"]
    assert [c["name"] for c in module.list_competitions({"pk": "a", "block_id": "block-2025"})] == ["2025 Provincials", "Directory meet"]


class FakeCompetitionTable:
    name = "competitions"

    def __init__(self):
        self.items = {("athlete-1", "COMP#meet"): {"pk": "athlete-1", "sk": "COMP#meet", "master_id": "meet", "revision": Decimal("0"), "notes": ""}}
        self.meta = type("Meta", (), {"client": self})()
        self.fail_after_commit = False

    def get_item(self, Key, ConsistentRead=False):
        item = self.items.get(tuple(Key.values()))
        return {"Item": copy.deepcopy(item)} if item is not None else {}

    def transact_write_items(self, TransactItems):
        update = TransactItems[0]["Update"]
        key = tuple(update["Key"].values())
        item = self.items[key]
        expected = int(update["ExpressionAttributeValues"][":expected"])
        if int(item.get("revision", 0)) != expected:
            raise ClientError({"Error": {"Code": "TransactionCanceledException", "Message": "condition failed"}}, "TransactWriteItems")
        item["revision"] = update["ExpressionAttributeValues"][":next"]
        item["updated_at"] = update["ExpressionAttributeValues"][":updated"]
        for name, field in update["ExpressionAttributeNames"].items():
            if name.startswith("#") and name not in {"#pk", "#revision", "#updated_at"}:
                value_key = f":value_{field}"
                if value_key in update["ExpressionAttributeValues"]:
                    item[field] = copy.deepcopy(update["ExpressionAttributeValues"][value_key])
        if " REMOVE " in update["UpdateExpression"]:
            for name in update["UpdateExpression"].split(" REMOVE ", 1)[1].split(", "):
                item.pop(update["ExpressionAttributeNames"][name.strip()], None)
        marker = TransactItems[1]["Put"]["Item"]
        self.items[(marker["pk"], marker["sk"])] = copy.deepcopy(marker)
        if self.fail_after_commit:
            self.fail_after_commit = False
            raise ClientError({"Error": {"Code": "InternalServerError", "Message": "lost response"}}, "TransactWriteItems")


def test_competition_cas_conflict_and_lost_response(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")
    table = FakeCompetitionTable()
    monkeypatch.setattr(module, "_get_table", lambda: table)
    first = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"notes": "first"}, "expected_revision": 0, "idempotency_key": "first"})
    assert first["revision"] == 1
    with pytest.raises(module.CompetitionConflictError) as conflict:
        module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"notes": "lost"}, "expected_revision": 0, "idempotency_key": "second"})
    assert conflict.value.current_revision == 1
    table.fail_after_commit = True
    replay = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"notes": "second"}, "expected_revision": 1, "idempotency_key": "second"})
    assert replay["notes"] == "second"
    assert replay["revision"] == 2


def test_competition_idempotency_rejects_changed_payload_and_keeps_attempt_ids(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")
    table = FakeCompetitionTable()
    monkeypatch.setattr(module, "_get_table", lambda: table)
    report = {"attempts": [{"lift": "squat", "attempt_number": 1, "kg": 100, "result": "made"}]}
    result = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"post_meet_report": report}, "expected_revision": 0, "idempotency_key": "report"})
    attempt_id = result["post_meet_report"]["attempts"][0]["attempt_id"]
    replay = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"post_meet_report": report}, "expected_revision": 1, "idempotency_key": "report"})
    assert replay["post_meet_report"]["attempts"][0]["attempt_id"] == attempt_id
    with pytest.raises(ValueError, match="different payload"):
        module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"notes": "changed"}, "expected_revision": 1, "idempotency_key": "report"})


def test_entering_a_meet_indexes_it_by_date_and_block_and_withdrawing_unindexes_it(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")
    table = FakeCompetitionTable()
    table.items[("athlete-1", "COMP#meet")]["start_date"] = "2026-11-01"
    monkeypatch.setattr(module, "_get_table", lambda: table)
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")
    monkeypatch.setattr(module, "_invalidate_analysis_cache", lambda pk: None)

    entered = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"user_status": "confirmed"}, "expected_revision": 0, "idempotency_key": "enter"})
    stored = table.items[("athlete-1", "COMP#meet")]
    assert (entered["entry_date"], entered["block_id"]) == ("2026-11-01", "block-new")
    assert (stored["entry_date"], stored["block_id"]) == ("2026-11-01", "block-new")

    withdrawn = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"user_status": "available"}, "expected_revision": 1, "idempotency_key": "withdraw"})
    assert "entry_date" not in withdrawn
    assert "entry_date" not in table.items[("athlete-1", "COMP#meet")]
