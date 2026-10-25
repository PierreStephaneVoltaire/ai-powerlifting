import copy
import importlib
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from botocore.exceptions import ClientError

from services.lib.program_store import ProgramStore, ProgramRevisionConflictError
setup = importlib.import_module("services.handlers.program.health_setup_initialize.core")


class SetupTable:
    def __init__(self, transaction_error=None):
        self.items = {}
        self.meta = type("Meta", (), {"client": self})()
        self.transaction_error = transaction_error
        self.lose_reply = False
        self.barrier = None
        self.lock = threading.RLock()

    def get_item(self, Key, **kwargs):
        with self.lock:
            item = self.items.get((Key["pk"], Key["sk"]))
            return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, Item, **kwargs):
        with self.lock:
            key = (Item["pk"], Item["sk"])
            assert key not in self.items
            self.items[key] = copy.deepcopy(Item)

    def query(self, **kwargs):
        with self.lock:
            items = sorted((copy.deepcopy(item) for item in self.items.values() if item['sk'].startswith('program#v')), key=lambda item: item['sk'])
        after = (kwargs.get('ExclusiveStartKey') or {}).get('sk', '')
        items = [item for item in items if item['sk'] > after]
        return {'Items': items[:1], **({'LastEvaluatedKey': {'pk': items[0]['pk'], 'sk': items[0]['sk']}} if len(items) > 1 else {})}

    def transact_write_items(self, TransactItems):
        if self.barrier:
            self.barrier.wait(timeout=5)
        with self.lock:
            if self.transaction_error:
                raise self.transaction_error
            pending = copy.deepcopy(self.items)
            for operation in TransactItems:
                if "Put" in operation:
                    item = operation["Put"]["Item"]
                    key = (item['pk'], item['sk'])
                    if key in pending:
                        raise ClientError({'Error': {'Code': 'TransactionCanceledException'}}, 'TransactWriteItems')
                    pending[key] = copy.deepcopy(item)
                else:
                    key = operation["Update"]["Key"]
                    item = pending[(key['pk'], key['sk'])]
                    assert item['published'] is False
                    item['published'] = True
            self.items = pending
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError('Response lost after commit')


def setup_fixture(monkeypatch):
    table = SetupTable()
    store = ProgramStore('health', 'athlete')
    store._table = table
    class Sessions:
        fail_once = False
        records = {}
        def replace_program_sessions_sync(self, key, sessions, *args, **kwargs):
            self.records[key] = copy.deepcopy(sessions[:1])
            if self.fail_once:
                self.fail_once = False
                raise ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException'}}, 'BatchWriteItem')
            self.records[key] = copy.deepcopy(sessions)
    sessions = Sessions()
    store._get_session_store = lambda: sessions
    monkeypatch.setattr(setup, '_store_for', lambda pk: store)
    monkeypatch.setattr(setup, '_setup_template', lambda sk, person: {'required_maxes': []} if person == 'person' else None)
    monkeypatch.setattr(setup, '_setup_concretize_template', lambda *args: [{'id': 'one', 'date': '2026-09-01'}, {'id': 'two', 'date': '2026-09-02'}])
    args = {'pk': 'athlete', '_person_pk': 'person', 'mode': 'template', 'template_sk': 'template#one', 'start_date': '2026-09-01', 'week_start_day': 'Monday', 'maxes': {'squat': 100, 'bench': 70, 'deadlift': 120}, 'expected_revision': 0, 'idempotency_key': 'setup'}
    return table, store, sessions, args


@pytest.mark.parametrize('failure', ['sessions', 'transaction'])
def test_setup_interruption_and_retry_publish_only_complete_sessions(monkeypatch, failure):
    table, store, sessions, args = setup_fixture(monkeypatch)
    if failure == 'sessions':
        sessions.fail_once = True
    else:
        table.transaction_error = ClientError({'Error': {'Code': 'TransactionCanceledException'}}, 'TransactWriteItems')
    with pytest.raises(ClientError):
        asyncio.run(setup.health_setup_initialize(args))
    assert not table.get_item(Key={'pk': 'athlete', 'sk': 'program#current'})
    assert setup._setup_current_program_sk(store) is None
    table.transaction_error = None
    result = asyncio.run(setup.health_setup_initialize(args))
    assert result['programSk'].startswith(store.PROGRAM_SK_PREFIX)
    assert len(sessions.records[result['programSk']]) == 2
    assert sum(item.get('published') is True for item in table.items.values()) == 1
    assert asyncio.run(setup.health_setup_initialize(args)) == result


def test_setup_lost_reply_and_same_key_retry_recover_committed_result(monkeypatch):
    table, store, sessions, args = setup_fixture(monkeypatch)
    table.lose_reply = True
    result = asyncio.run(setup.health_setup_initialize(args))
    assert asyncio.run(setup.health_setup_initialize(args)) == result
    assert len(sessions.records) == 1
    assert table.items[('athlete', 'program#current')]['ref_sk'] == result['programSk']
    with pytest.raises(ValueError, match='different payload'):
        asyncio.run(setup.health_setup_initialize({**args, 'program_name': 'Different'}))


@pytest.mark.parametrize('same_key', [False, True])
def test_racing_initializations_have_one_published_program(monkeypatch, same_key):
    table, store, sessions, args = setup_fixture(monkeypatch)
    table.barrier = threading.Barrier(2)
    def initialize(key):
        try:
            return asyncio.run(setup.health_setup_initialize({**args, 'idempotency_key': key}))
        except ProgramRevisionConflictError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(initialize, ['setup', 'setup' if same_key else 'other']))
    successes = [result for result in results if isinstance(result, dict)]
    assert len(successes) == (2 if same_key else 1)
    assert len({result['programSk'] for result in successes}) == 1
    assert sum(item.get('published') is True for item in table.items.values()) == 1
    if not same_key:
        assert next(result for result in results if isinstance(result, ProgramRevisionConflictError)).current_revision == 1


def test_setup_status_scans_past_hidden_stages_in_both_handlers(monkeypatch):
    table, store, sessions, args = setup_fixture(monkeypatch)
    status = importlib.import_module('services.handlers.program.health_setup_status.core')
    monkeypatch.setattr(status, '_store_for', lambda pk: store)
    table.items[('athlete', 'program#v001-a')] = {'pk': 'athlete', 'sk': 'program#v001-a', 'published': False}
    table.items[('athlete', 'program#v001-b')] = {'pk': 'athlete', 'sk': 'program#v001-b', 'published': True}
    for module in (status, setup):
        assert asyncio.run(module.health_setup_status(args))['currentProgramSk'] == 'program#v001-b'


def test_new_version_rejects_whole_meta_and_missing_logged_id():
    store = ProgramStore.__new__(ProgramStore)
    for path in ('meta', 'meta.revision', 'meta.new_version_idempotency', 'meta.transition_idempotency', 'meta.current_block_id', 'meta.blocks'):
        with pytest.raises(ValueError, match="Protected"):
            store._validate_version_patches({"meta": {}}, [{"path": path, "value": {}}])
    store._validate_version_patches({"meta": {}}, [{"path": "meta.program_name", "value": "Next cycle"}])
    with pytest.raises(ValueError, match="stable session id"):
        store._preserve_logged_sessions({"sessions": [{"status": "planned", "exercises": [{"set_statuses": ["failed"]}]}]}, {"sessions": [{}]})


@pytest.mark.parametrize('status', ['completed', 'failed', 'skipped'])
def test_new_version_detects_partial_performed_sets_and_preserves_media(status):
    store = ProgramStore.__new__(ProgramStore)
    old = {"sessions": [{"id": "s1", "status": "planned", "exercises": [{"set_statuses": ["pending", status]}], "videos": [{"id": "v1"}]}]}
    new = copy.deepcopy(old)
    new["sessions"][0]["planned_exercises"] = []
    store._validate_version_patches(old, [{"path": "sessions[0].planned_exercises", "value": []}])
    store._preserve_logged_sessions(old, new)
    assert new["sessions"][0]["id"] == "s1"
    assert new["sessions"][0]["videos"] == [{"id": "v1"}]
    with pytest.raises(ValueError, match="Logged session"):
        store._validate_version_patches(old, [{"path": "sessions[0].exercises", "value": []}])


def test_new_version_write_failure_is_reported_without_replay():
    store = ProgramStore("health", "athlete")
    table = SetupTable()
    table.items[("athlete", "program#current")] = {"pk": "athlete", "sk": "program#current", "ref_sk": "program#v002"}
    table.items[("athlete", "program#v002")] = {"pk": "athlete", "sk": "program#v002", "meta": {}}
    store._table = table
    store._write_new_version_sync = lambda *args: (_ for _ in ()).throw(ClientError({"Error": {"Code": "InternalServerError"}}, "PutItem"))
    with pytest.raises(RuntimeError, match="Failed to write new version"):
        asyncio.run(store._write_new_version({"meta": {}}, False))
    assert table.items[("athlete", "program#current")]["ref_sk"] == "program#v002"
