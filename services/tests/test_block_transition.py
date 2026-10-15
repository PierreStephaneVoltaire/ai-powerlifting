import asyncio
import copy
import hashlib
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[2]
LAYER_PATHS = [
    ROOT / "lambda/layers/pl-program/python",
    ROOT / "lambda/layers/pl-sessions/python",
    ROOT / "lambda/layers/pl-core/python",
]
for path in LAYER_PATHS:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from program_store import ProgramNotFoundError, ProgramRevisionConflictError, ProgramStore
from session_store import SessionIdentityConflictError


class TransactionCanceledException(ClientError):
    def __init__(self, message):
        super().__init__({"Error": {"Code": "TransactionCanceledException", "Message": message}}, "TransactWriteItems")


class FakeTable:
    def __init__(self, items):
        self.items = {tuple(item[key] for key in ("pk", "sk")): copy.deepcopy(item) for item in items}
        self.meta = SimpleNamespace(client=SimpleNamespace(transact_write_items=self.transact_write_items))
        self.conflict_next = False
        self.puts = []
        self.deletes = []
        self.transaction_lock = threading.Lock()
        self.transaction_barrier = None

    def get_item(self, Key, **_kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, Item, **_kwargs):
        item = copy.deepcopy(Item)
        self.items[(item["pk"], item["sk"])] = item
        self.puts.append(item)

    def delete_item(self, Key, **_kwargs):
        self.items.pop((Key["pk"], Key["sk"]), None)
        self.deletes.append(dict(Key))

    def query(self, **_kwargs):
        return {"Items": [
            copy.deepcopy(item)
            for (pk, sk), item in self.items.items()
            if pk == "athlete-1" and sk.startswith("program#v")
        ]}

    def transact_write_items(self, TransactItems):
        if self.conflict_next:
            self.conflict_next = False
            pointer = self.items[("athlete-1", "program#current")]
            pointer["revision"] = int(pointer.get("revision", 0)) + 1
            raise TransactionCanceledException("conditional check failed")
        if self.transaction_barrier is not None:
            self.transaction_barrier.wait()
        with self.transaction_lock:
            pending = copy.deepcopy(self.items)
            for operation in TransactItems:
                if "Put" in operation:
                    put = operation["Put"]
                    item = copy.deepcopy(put["Item"])
                    current = pending.get((item["pk"], item["sk"]))
                    expected = put["ExpressionAttributeValues"][":revision"]
                    if current and int(current.get("revision", 0)) != int(expected):
                        raise TransactionCanceledException("conditional check failed")
                    pending[(item["pk"], item["sk"])] = item
                else:
                    update = operation["Update"]
                    key = dict(update["Key"])
                    current = pending.get((key["pk"], key["sk"]))
                    if not current or current.get("published", True) is not False:
                        raise TransactionCanceledException("conditional check failed")
                    current["published"] = update["ExpressionAttributeValues"][":published"]
            self.items = pending


class FakeSessionStore:
    def __init__(self, sessions):
        self.sessions = {"program#v007": copy.deepcopy(sessions)}
        self.replacements = []
        self.on_replace = None

    def list_sessions_sync(self, program_sk, _phases):
        return copy.deepcopy(self.sessions.get(program_sk, []))

    def replace_program_sessions_sync(self, program_sk, sessions, phases, **_kwargs):
        self.sessions[program_sk] = copy.deepcopy(sessions)
        self.replacements.append((program_sk, copy.deepcopy(sessions), copy.deepcopy(phases)))
        if self.on_replace:
            self.on_replace(program_sk)


def make_store():
    sessions = [
        {"id": "logged", "date": "2026-09-10", "block": "current", "block_id": "current", "status": "logged", "completed": True, "week_number": 4, "session_notes": "kept"},
        {"id": "planned", "date": "2026-09-20", "block": "current", "block_id": "current", "status": "planned", "completed": False, "week_number": 5},
        {"id": "skipped", "date": "2026-09-21", "block": "current", "block_id": "current", "status": "skipped", "completed": False, "week_number": 5},
    ]
    program = {
        "pk": "athlete-1",
        "sk": "program#v007",
        "meta": {
            "revision": 4,
            "version_label": "7.0",
            "program_week_start_day": "Monday",
            "block_week_start_days": {"current": "Tuesday"},
            "block_start_maxes": {"current": {"squat_kg": 180, "bench_kg": 110, "deadlift_kg": 210}},
            "block_notes": [{"date": "2026-09-01", "notes": "keep this history", "updated_at": "2026-09-01T00:00:00+00:00", "block": "current"}],
            "blocks": [{"id": "current", "name": "Accumulation", "status": "active", "start_week": 1, "end_week": 4}],
        },
        "phases": [{"name": "Volume", "intent": "base", "start_week": 2, "end_week": 4, "notes": "phase history", "block": "current"}],
        "current_maxes": {"squat": 185, "bench": 115, "deadlift": 220},
    }
    pointer = {"pk": "athlete-1", "sk": "program#current", "version": 7, "ref_sk": "program#v007", "revision": 4}
    table = FakeTable([pointer, program])
    sessions_store = FakeSessionStore(sessions)
    store = ProgramStore("if-health", "athlete-1")
    store._table = table
    store._invalidate_analysis_cache = lambda: None
    store._get_session_store = lambda: sessions_store
    return store, table, sessions_store


def transition(store, **kwargs):
    return asyncio.run(store.block_transition(**kwargs))


def test_complete_and_start_preserves_history_resets_numbering_and_sessions():
    store, table, sessions_store = make_store()
    result = transition(
        store,
        action="complete_and_start",
        block_id="current",
        expected_revision=4,
        idempotency_key="transition-1",
        name="Strength",
        start_date="2026-09-22",
        week_start_day="Wednesday",
        start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
    )

    program = result["program"]
    meta = program["meta"]
    next_id = f"block-{hashlib.sha256(b'transition-1').hexdigest()[:16]}"
    archive_id = next(block["id"] for block in meta["blocks"] if block["status"] == "completed")
    assert result["revision"] == 5
    assert meta["current_block_id"] == next_id
    assert [block["label"] for block in meta["blocks"]].count("current") == 1
    assert [block["id"] for block in meta["blocks"]].count(next_id) == 1
    assert archive_id != "current"
    assert next(block["status"] for block in meta["blocks"] if block["id"] == archive_id) == "completed"
    assert next(block["start_week"] for block in meta["blocks"] if block["id"] == next_id) == 1
    assert next(block["end_week"] for block in meta["blocks"] if block["id"] == next_id) == 0
    assert meta["block_start_maxes"][archive_id] == {"squat_kg": 180, "bench_kg": 110, "deadlift_kg": 210}
    assert meta["block_start_maxes"][next_id] == {"squat": 190, "bench": 120, "deadlift": 225}
    assert meta["block_week_start_days"] == {archive_id: "Tuesday", next_id: "Wednesday"}
    assert meta["block_notes"][0]["notes"] == "keep this history"
    assert meta["block_notes"][0]["block"] == archive_id
    phases = [phase for phase in program["phases"] if phase["block"] == next_id]
    assert phases == []
    assert [(session["id"], session["status"], session["completed"]) for session in program["sessions"]] == [
        ("logged", "logged", True),
        ("planned", "planned", False),
        ("skipped", "skipped", False),
    ]
    assert {session["block"] for session in program["sessions"]} == {archive_id}
    assert len(sessions_store.replacements) == 1
    assert len([item for item in table.items.values() if item.get("sk", "").startswith("program#v") and item.get("published", True) is not False]) == 2


def test_empty_new_block_template_preserves_external_session_rows():
    store, _, sessions_store = make_store()
    result = transition(
        store,
        action="complete_and_start",
        block_id="current",
        expected_revision=4,
        idempotency_key="empty-template-1",
        name="Empty next block",
        start_date="2026-09-22",
        week_start_day="Wednesday",
        start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
        next_program={"phases": [], "sessions": []},
    )
    preserved = next(session for session in result["program"]["sessions"] if session["id"] == "logged")
    assert preserved["session_notes"] == "kept"
    assert preserved["completed"] is True
    assert sessions_store.sessions["program#v007"][0]["id"] == "logged"


def test_retry_is_idempotent_and_creates_one_archive_and_next_block():
    store, table, _ = make_store()
    args = {
        "action": "complete_and_start",
        "block_id": "current",
        "expected_revision": 4,
        "idempotency_key": "transition-retry",
        "name": "Strength",
        "start_date": "2026-09-22",
        "week_start_day": "Wednesday",
        "start_maxes_kg": {"squat": 190, "bench": 120, "deadlift": 225},
    }
    first = transition(store, **args)
    second = transition(store, **args)
    assert second["revision"] == first["revision"] == 5
    assert second["next_block_id"] == first["next_block_id"]
    assert len(second["program"]["meta"]["blocks"]) == 2
    assert len([item for item in table.items.values() if item.get("sk", "").startswith("program#v")]) == 2


def test_template_replay_uses_outer_payload_before_current_block_changes():
    store, table, _ = make_store()
    args = {
        "action": "complete_and_start",
        "block_id": "current",
        "expected_revision": 4,
        "idempotency_key": "template-replay",
        "start_date": "2026-09-22",
        "week_start_day": "Wednesday",
        "start_maxes_kg": {"squat": 190},
        "next_program": {"phases": [], "sessions": []},
        "template_payload_hash": "outer-payload",
        "template_preserved_sessions": 3,
    }
    first = transition(store, **args)
    replay = transition(store, **{**args, "block_id": first["next_block_id"], "template_payload_hash": "outer-payload"})
    assert replay["revision"] == first["revision"] == 5
    assert replay["next_block_id"] == first["next_block_id"]
    assert replay["program"]["meta"]["current_block_id"] == first["next_block_id"]
    assert len(replay["program"]["meta"]["blocks"]) == 2
    assert len([item for item in table.items.values() if item.get("sk", "").startswith("program#v")]) == 2
    with pytest.raises(ValueError, match="different payload"):
        transition(store, **{**args, "template_payload_hash": "changed-payload"})


def test_revision_conflict_removes_uncommitted_staged_version_from_history():
    store, table, _ = make_store()
    table.conflict_next = True
    with pytest.raises(ProgramRevisionConflictError) as error:
        transition(
            store,
            action="complete",
            block_id="current",
            expected_revision=4,
            idempotency_key="transition-conflict",
        )
    assert error.value.expected_revision == 4
    assert error.value.current_revision == 5
    assert [item["sk"] for item in store._list_programs_sync(include_archived=True)] == ["program#v007"]
    assert any(item.get("published") is False for item in table.items.values())


def test_complete_and_start_backfills_historical_start_maxes_from_block():
    store, _, _ = make_store()
    program = store._table.items[("athlete-1", "program#v007")]
    del program["meta"]["block_start_maxes"]
    program["meta"]["blocks"][0]["start_maxes_kg"] = {"squat": 175, "bench": 105, "deadlift": 205}
    result = transition(
        store,
        action="complete_and_start",
        block_id="current",
        expected_revision=4,
        idempotency_key="transition-old-maxes",
        start_date="2026-09-22",
        week_start_day="Wednesday",
        start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
    )
    archive_id = next(block["id"] for block in result["program"]["meta"]["blocks"] if block["status"] == "completed")
    assert result["program"]["meta"]["block_start_maxes"][archive_id] == {"squat": 175, "bench": 105, "deadlift": 205}


def test_start_next_requires_completed_block_and_uses_designer_plan():
    store, _, sessions_store = make_store()
    with pytest.raises(ValueError, match="only allowed"):
        transition(
            store,
            action="start_next",
            block_id="current",
            expected_revision=4,
            idempotency_key="start-too-soon",
            start_date="2026-09-22",
            week_start_day="Wednesday",
            start_maxes_kg={"squat": 190},
        )
    completed = transition(store, action="complete", block_id="current", expected_revision=4, idempotency_key="complete-first")
    archive_id = completed["program"]["meta"]["blocks"][0]["id"]
    result = transition(
        store,
        action="start_next",
        block_id=archive_id,
        expected_revision=5,
        idempotency_key="start-second",
        name="Strength",
        start_date="2026-09-22",
        week_start_day="Wednesday",
        start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
        next_program={
            "phases": [{"name": "Strength", "start_week": 1, "end_week": 3}],
            "sessions": [{"id": "next-session", "date": "2026-09-22", "week_number": 1, "status": "planned"}],
        },
    )
    next_id = result["next_block_id"]
    assert result["program"]["meta"]["current_block_id"] == next_id
    assert [phase["start_week"] for phase in result["program"]["phases"] if phase["block"] == "current"] == [1]
    next_session = next(session for session in result["program"]["sessions"] if session["id"] == "next-session")
    assert next_session["block"] == "current"
    assert next_session["block_id"] == next_id
    assert next_session["status"] == "planned"
    assert next_session["completed"] is False
    assert len(sessions_store.replacements) == 2


def test_unknown_block_and_invalid_next_plan_are_rejected():
    store, _, _ = make_store()
    with pytest.raises(ValueError, match="active current"):
        transition(store, action="complete", block_id="missing", expected_revision=4, idempotency_key="unknown")
    with pytest.raises(ValueError, match="completed sessions"):
        transition(
            store,
            action="complete_and_start",
            block_id="current",
            expected_revision=4,
            idempotency_key="bad-plan",
            start_date="2026-09-22",
            week_start_day="Wednesday",
            start_maxes_kg={"squat": 190},
            next_program={"sessions": [{"date": "2026-09-22", "status": "logged"}]},
        )


def test_transition_rejects_next_session_id_colliding_with_archived_history():
    store, table, sessions_store = make_store()
    with pytest.raises(SessionIdentityConflictError, match="occurs more than once"):
        transition(
            store,
            action="complete_and_start",
            block_id="current",
            expected_revision=4,
            idempotency_key="collision-transition",
            start_date="2026-09-22",
            week_start_day="Wednesday",
            start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
            next_program={"sessions": [{"id": "logged", "date": "2026-09-22", "week_number": 1}]},
        )
    assert not sessions_store.replacements
    assert len([item for item in table.items.values() if item.get("sk", "").startswith("program#v")]) == 1


def test_new_version_rejects_full_program_duplicate_before_staging():
    store, table, _ = make_store()
    duplicate = copy.deepcopy(store._table.items[("athlete-1", "program#v007")])
    duplicate["sessions"] = [{"id": "same", "date": "2026-09-10"}, {"id": "same", "date": "2026-09-11"}]

    with pytest.raises(SessionIdentityConflictError, match="occurs more than once"):
        store._write_new_version_sync(duplicate, minor=False, expected_revision=4, idempotency_key="duplicate-stage")
    assert len([item for item in table.items.values() if item.get("sk", "").startswith("program#v")]) == 1


def test_unpublished_stages_are_hidden_from_lists_and_reads():
    store, table, _ = make_store()
    table.conflict_next = True
    with pytest.raises(ProgramRevisionConflictError):
        transition(store, action="complete", block_id="current", expected_revision=4, idempotency_key="stage-hidden")
    staged = [item for item in table.items.values() if item.get("published") is False]
    assert len(staged) == 1
    assert all(item["sk"] not in {p["sk"] for p in store._list_programs_sync(include_archived=True)} for item in staged)
    store._selected_program_sk = staged[0]["sk"]
    with pytest.raises(ProgramNotFoundError):
        store._load_program_sync()


def test_ordinary_new_version_advances_existing_revision():
    store, table, _ = make_store()
    result = asyncio.run(store.new_version([], "ordinary change", 4, "ordinary-change"))
    assert result["meta"]["revision"] == 5
    assert table.items[("athlete-1", "program#current")]["revision"] == 5


def test_concurrent_different_payloads_stage_distinct_unpublished_versions():
    first, table, _ = make_store()
    second, _, _ = make_store()
    second._table = table
    table.transaction_barrier = threading.Barrier(2)
    async def race():
        return await asyncio.gather(
            first.block_transition(action="complete", block_id="current", expected_revision=4, idempotency_key="race-one"),
            second.block_transition(action="complete", block_id="current", expected_revision=4, idempotency_key="race-two"),
            return_exceptions=True,
        )
    results = asyncio.run(race())
    assert sum(isinstance(result, ProgramRevisionConflictError) for result in results) == 1
    staged = [item for item in table.items.values() if item.get("published") is False]
    assert len(staged) == 1
    assert staged[0]["sk"] != "program#v008"


def test_transition_rejects_session_log_written_after_staging():
    store, table, sessions_store = make_store()

    def log_session_after_stage(program_sk):
        if program_sk == "program#v007":
            return
        pointer = table.items[("athlete-1", "program#current")]
        pointer["revision"] = 5
        table.items[("athlete-1", "program#v007")]["meta"]["revision"] = 5
        sessions_store.sessions["program#v007"][0]["session_notes"] = "logged during transition"

    sessions_store.on_replace = log_session_after_stage
    with pytest.raises(ProgramRevisionConflictError):
        transition(
            store,
            action="complete",
            block_id="current",
            expected_revision=4,
            idempotency_key="session-race",
        )
    assert sessions_store.sessions["program#v007"][0]["session_notes"] == "logged during transition"
    assert table.items[("athlete-1", "program#current")]["ref_sk"] == "program#v007"
    staged = [item for item in table.items.values() if item.get("published") is False]
    assert len(staged) == 1


def test_complete_archives_current_block_under_name_slug():
    store, _table, _sessions = make_store()

    result = transition(store, action="complete", block_id="current", expected_revision=4, idempotency_key="archive-1", current_name="Sunny Daze + APEX Prep")

    meta = result["program"]["meta"]
    archived = meta["blocks"][0]
    assert archived["id"] == "sunny-daze-apex-prep"
    assert archived["name"] == archived["label"] == "Sunny Daze + APEX Prep"
    assert archived["status"] == "completed"
    assert meta["current_block_id"] is None
    assert {session["block"] for session in result["program"]["sessions"]} == {"sunny-daze-apex-prep"}


@pytest.mark.parametrize("name", ["current", "Current Block", " CURRENT "])
def test_archived_block_cannot_be_named_current(name):
    store, _table, _sessions = make_store()

    with pytest.raises(ValueError, match="cannot be named current"):
        transition(store, action="complete", block_id="current", expected_revision=4, idempotency_key="archive-2", current_name=name)

    archived = transition(store, action="complete", block_id="current", expected_revision=4, idempotency_key="archive-3")
    archive_id = archived["program"]["meta"]["blocks"][0]["id"]
    with pytest.raises(ValueError, match="cannot be named current"):
        transition(store, action="rename", block_id=archive_id, expected_revision=5, idempotency_key="rename-1", name=name)


def _apply_mutations_in_memory(store):
    async def mutate_source(_name, _payload, _expected_revision, _idempotency_key, mutate):
        program = copy.deepcopy(await store.get_program())
        result = mutate(program)
        store.get_program = _returning(program)
        return result

    store.mutate_source = mutate_source


def _returning(program):
    async def get_program():
        return copy.deepcopy(program)

    return get_program


def _store_with_block_records():
    store, table, sessions_store = make_store()
    program = table.items[("athlete-1", "program#v007")]
    program["diet_notes"] = [{"date": "2026-09-05", "notes": "old cut"}]
    program["supplements"] = [{"name": "creatine", "dose": "5g"}]
    program["supplement_phases"] = [{"phase": 1, "phase_name": "Base", "notes": "", "items": [], "block": "current"}]
    return store, table


def test_complete_and_start_archives_notes_and_supplements_with_the_block():
    store, _table = _store_with_block_records()
    result = transition(
        store,
        action="complete_and_start",
        block_id="current",
        expected_revision=4,
        idempotency_key="transition-records",
        name="Strength",
        start_date="2026-09-22",
        week_start_day="Wednesday",
        start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
    )
    program = result["program"]
    archive_id = next(block["id"] for block in program["meta"]["blocks"] if block["status"] == "completed")
    assert program["diet_notes"][0]["block_id"] == archive_id
    assert program["supplements"][0]["block_id"] == archive_id
    assert program["supplement_phases"][0]["block"] == archive_id

    store.get_program = _returning(program)
    _apply_mutations_in_memory(store)
    upserted = asyncio.run(store.upsert_diet_note("2026-09-05", "new block note", 5, "note-1"))
    assert [note["notes"] for note in upserted["diet_notes"]] == ["new block note"]
    assert upserted["note"]["block_id"] == program["meta"]["current_block_id"]


def test_replacing_current_block_supplements_keeps_archived_ones():
    store, _table = _store_with_block_records()
    transitioned = transition(
        store,
        action="complete_and_start",
        block_id="current",
        expected_revision=4,
        idempotency_key="transition-supps",
        name="Strength",
        start_date="2026-09-22",
        week_start_day="Wednesday",
        start_maxes_kg={"squat": 190, "bench": 120, "deadlift": 225},
    )
    store.get_program = _returning(transitioned["program"])
    _apply_mutations_in_memory(store)
    result = asyncio.run(store.update_supplements({"supplements": [{"name": "caffeine", "dose": "200mg"}]}, 5, "supps-1"))
    assert [item["name"] for item in result["supplements"]] == ["caffeine"]
    stored = asyncio.run(store.get_program())
    assert sorted(item["name"] for item in stored["supplements"]) == ["caffeine", "creatine"]
