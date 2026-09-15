from services.contract import load_operations
from services.dispatch import authorize, OperationError
import pytest


def test_trusted_scope_overrides_empty_pk_and_rejects_other_athlete():
    operation = load_operations("program")["program_get"]
    assert authorize(operation, {"pk": ""}, "athlete-a", "person-a")["pk"] == "athlete-a"
    with pytest.raises(OperationError):
        authorize(operation, {"pk": "athlete-b"}, "athlete-a", "person-a")


def test_template_actor_is_person_separate_from_selected_athlete():
    operation = load_operations('templates')['template_copy']
    payload = {'sk': 'template#source', 'new_name': 'Copy', 'expected_revision': 2, 'idempotency_key': 'copy', 'actor_pk': 'person-a'}
    scoped = authorize(operation, payload, 'athlete-a', 'person-a')
    operation.validate_input(scoped)
    assert scoped['actor_pk'] == 'person-a' and scoped['pk'] == 'athlete-a'
    with pytest.raises(OperationError):
        authorize(operation, {**payload, 'actor_pk': 'athlete-a'}, 'athlete-a', 'person-a')


def test_program_store_does_not_retarget_another_request(monkeypatch):
    import program_tool_helpers
    first = program_tool_helpers.get_store({"pk": "athlete-a", "program_sk": "program#v001"})
    second = program_tool_helpers.get_store({"pk": "athlete-b"})
    assert first is not second
    assert first.pk == "athlete-a"
    assert second.pk == "athlete-b"
    assert first._current_program_sk_sync() == "program#v001"


def test_nested_store_constructors_inherit_only_current_athlete(monkeypatch):
    import sys
    from types import SimpleNamespace
    from concurrent.futures import ThreadPoolExecutor
    from services.contract import Operation
    from services.dispatch import dispatch
    from program_store import ProgramStore
    from glossary_store import GlossaryStore
    from storage_scope import current_athlete

    def handler(arguments, context):
        return [ProgramStore('unused').pk, GlossaryStore('unused').pk]

    monkeypatch.setitem(sys.modules, 'lambda.scope_canary.handler', SimpleNamespace(handler=handler))
    operation = Operation(name='scope_canary', domain='program', description='scope check', handler='lambda.scope_canary.handler', input_schema={'type': 'object'}, result_schema={'type': 'array'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(dispatch, operation, {'pk': athlete}) for athlete in ('athlete-a', 'athlete-b')]
        assert [future.result() for future in futures] == [['athlete-a', 'athlete-a'], ['athlete-b', 'athlete-b']]
    assert current_athlete.get() is None
