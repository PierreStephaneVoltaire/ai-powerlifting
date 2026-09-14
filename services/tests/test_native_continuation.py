from types import SimpleNamespace
import asyncio
import json

import pytest
from jsonschema import ValidationError

from services import execution
from services.ai import completion
from services.contract import Operation
from services.dispatch import dispatch


def test_domain_ai_resumes_same_execution_without_nested_queue(monkeypatch):
    writes = []

    def handler(operation, arguments):
        response = asyncio.run(completion({'messages': [{'role': 'user', 'content': 'Return a value'}], 'tools': [{'type': 'function', 'function': {'name': 'answer', 'parameters': {'type': 'object', 'properties': {'value': {'type': 'number'}}, 'required': ['value']}}}]}))
        answer = json.loads(response.json()['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        writes.append((arguments['pk'], answer['value']))
        return answer

    monkeypatch.setattr(execution, 'dispatch', handler)

    async def check():
        pending = await execution.start(SimpleNamespace(name="test_operation"), {'pk': 'athlete-a'}, 'athlete-a', 'job-a')
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
        root = execution.DomainExecution(job_id='job-a', athlete='athlete-a')
        root.future = asyncio.create_task(asyncio.sleep(60))
        execution.executions[root.execution_id] = root
        execution.job_executions[root.job_id] = root
        try:
            nested = asyncio.create_task(execution.dispatch_nested(None, {'pk': 'athlete-a'}, 'athlete-a', 'job-a'))
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
        handler='lambda.private_metadata.handler',
        input_schema={'type': 'object', 'properties': {'pk': {'type': 'string'}}, 'required': ['pk'], 'additionalProperties': False},
        result_schema={'type': 'object'},
    )
    import services.dispatch as dispatch_module
    monkeypatch.setattr(dispatch_module.importlib, 'import_module', lambda _name: type('Module', (), {'handler': staticmethod(lambda arguments, _context: arguments)})())
    result = dispatch(operation, {'pk': 'athlete-a', '_if_job_id': 'job-a', '_person_pk': 'person-a'})
    assert result['_if_job_id'] == 'job-a'
    with pytest.raises(ValidationError):
        dispatch(operation, {'pk': 'athlete-a', 'unexpected': True})
