from types import SimpleNamespace
import asyncio
import json

import pytest
from jsonschema import ValidationError

from services.runtime import ai, execution
from services.runtime.ai import completion
from services.runtime import prompt_cache


@pytest.fixture(autouse=True)
def prompt_cache_store(monkeypatch):
    store = {"exact": None, "remembered": []}
    monkeypatch.setattr(prompt_cache, "exact", lambda *_args: store["exact"])
    monkeypatch.setattr(prompt_cache, "remember", lambda *args: store["remembered"].append(args))
    return store
from services.runtime.contract import Operation
from services.runtime.dispatch import dispatch


def test_domain_ai_resumes_same_execution_without_nested_queue(monkeypatch):
    writes = []

    def handler(operation, arguments):
        response = asyncio.run(completion({'messages': [{'role': 'user', 'content': 'Return a value'}], 'tools': [{'type': 'function', 'function': {'name': 'answer', 'parameters': {'type': 'object', 'properties': {'value': {'type': 'number'}}, 'required': ['value']}}}]}))
        answer = json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        writes.append((arguments['pk'], answer['value']))
        return answer

    monkeypatch.setattr(execution, 'dispatch', handler)

    async def check():
        pending = await execution.start(SimpleNamespace(name="test_operation"), {'pk': 'athlete-a', '_person_pk': 'person-a'}, 'athlete-a', 'job-a')
        assert pending['status'] == 'needs_inference'
        with pytest.raises(execution.OperationError):
            await execution.resume(pending['execution_id'], 'job-b', 'athlete-a')
        with pytest.raises(ValidationError):
            await execution.resume(pending['execution_id'], 'job-a', 'athlete-a', pending['challenge_id'], {'value': 'wrong'})
        assert writes == []
        result = await execution.resume(pending['execution_id'], 'job-a', 'athlete-a', pending['challenge_id'], {'value': 3})
        while result['status'] == 'running':
            result = await execution.resume(pending['execution_id'], 'job-a', 'athlete-a')
        assert result == {'status': 'succeeded', 'result': {'value': 3}}
        with pytest.raises(execution.OperationError):
            await execution.resume(pending['execution_id'], 'job-a', 'athlete-a')

    asyncio.run(check())
    assert writes == [('athlete-a', 3)]


def test_nested_operation_uses_the_root_execution_for_native_inference(monkeypatch):
    def handler(operation, arguments):
        response = asyncio.run(completion({'messages': [{'role': 'user', 'content': 'Return a value'}], 'tools': [{'type': 'function', 'function': {'name': 'answer', 'parameters': {'type': 'object', 'properties': {'value': {'type': 'number'}}, 'required': ['value']}}}]}))
        return json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])

    monkeypatch.setattr(execution, 'dispatch', handler)

    async def check():
        root = execution.DomainExecution(job_id='job-a', athlete='athlete-a', person='person-a', operation='test_operation')
        root.future = asyncio.create_task(asyncio.sleep(60))
        execution.executions[root.execution_id] = root
        execution.job_executions[root.job_id] = root
        try:
            nested = asyncio.create_task(execution.dispatch_nested(None, {'pk': 'athlete-a', '_person_pk': 'person-a'}, 'athlete-a', 'job-a'))
            for _ in range(100):
                if root.challenge:
                    break
                await asyncio.sleep(0.01)
            assert root.challenge
            execution.answer(root, root.challenge['challenge_id'], {'value': 3})
            assert await nested == {'value': 3}
        finally:
            root.future.cancel()
            execution.executions.pop(root.execution_id, None)
            execution.job_executions.pop(root.job_id, None)

    asyncio.run(check())


def test_nested_deterministic_operation_runs_when_root_execution_is_in_another_service(monkeypatch):
    monkeypatch.setattr(execution, 'dispatch', lambda operation, arguments: {'pk': arguments['pk']})

    class Operation:
        execution = 'deterministic'

    result = asyncio.run(execution.dispatch_nested(Operation(), {'pk': 'athlete-a'}, 'athlete-a', 'job-in-analytics'))
    assert result == {'pk': 'athlete-a'}


def test_dispatch_keeps_private_execution_metadata_out_of_public_contract_validation(monkeypatch):
    operation = Operation(
        name='private_metadata',
        domain='analytics',
        description='private metadata validation',
        handler='services.private_metadata.handler',
        input_schema={'type': 'object', 'properties': {'pk': {'type': 'string'}}, 'required': ['pk'], 'additionalProperties': False},
        result_schema={'type': 'object'},
    )
    import services.runtime.dispatch as dispatch_module
    monkeypatch.setattr(dispatch_module.importlib, 'import_module', lambda _name: type('Module', (), {'handler': staticmethod(lambda arguments, _context: arguments)})())
    result = dispatch(operation, {'pk': 'athlete-a', '_if_job_id': 'job-a', '_person_pk': 'person-a'})
    assert result['_if_job_id'] == 'job-a'
    with pytest.raises(ValidationError):
        dispatch(operation, {'pk': 'athlete-a', 'unexpected': True})


ANSWER_TOOLS = [{'type': 'function', 'function': {'name': 'answer', 'parameters': {'type': 'object', 'properties': {'value': {'type': 'number'}}, 'required': ['value']}}}]
CACHED = {'choices': [{'message': {'role': 'assistant', 'content': '{"value": 7}', 'tool_calls': [{'id': 'saved', 'type': 'function', 'function': {'name': 'answer', 'arguments': '{"value": 7}'}}]}, 'finish_reason': 'tool_calls'}]}


def _value_operation(monkeypatch):
    def handler(operation, arguments):
        response = asyncio.run(completion({'messages': [{'role': 'user', 'content': 'Return a value'}], 'tools': ANSWER_TOOLS}))
        return json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])

    monkeypatch.setattr(execution, 'dispatch', handler)


async def _finish(result, execution_id):
    while result['status'] == 'running':
        await asyncio.sleep(0.01)
        result = await execution.resume(execution_id, 'job-a', 'athlete-a')
    return result


def test_identical_prompt_reuses_the_saved_answer_without_delegating(monkeypatch, prompt_cache_store):
    _value_operation(monkeypatch)
    prompt_cache_store["exact"] = CACHED

    async def check():
        started = await execution.start(SimpleNamespace(name="test_operation"), {'pk': 'athlete-a', '_person_pk': 'person-a'}, 'athlete-a', 'job-a')
        assert started['status'] != 'needs_inference'
        return started if started['status'] == 'succeeded' else await _finish(started, started['execution_id'])

    assert asyncio.run(check()) == {'status': 'succeeded', 'result': {'value': 7}}
    assert prompt_cache_store["remembered"] == []


def test_cache_miss_delegates_once_and_saves_the_answer(monkeypatch, prompt_cache_store):
    _value_operation(monkeypatch)

    async def check():
        pending = await execution.start(SimpleNamespace(name="test_operation"), {'pk': 'athlete-a', '_person_pk': 'person-a'}, 'athlete-a', 'job-a')
        assert pending['status'] == 'needs_inference' and pending['instruction'] == ai.SPECIALIST_INSTRUCTION
        result = await execution.resume(pending['execution_id'], 'job-a', 'athlete-a', pending['challenge_id'], {'value': 3})
        return await _finish(result, pending['execution_id'])

    assert asyncio.run(check()) == {'status': 'succeeded', 'result': {'value': 3}}
    [(athlete, operation, request, response)] = prompt_cache_store["remembered"]
    assert (athlete, operation) == ('athlete-a', 'test_operation')
    assert request['messages'] == [{'role': 'user', 'content': 'Return a value'}]
    assert json.loads(response['choices'][0]['message']['content']) == {'value': 3}

