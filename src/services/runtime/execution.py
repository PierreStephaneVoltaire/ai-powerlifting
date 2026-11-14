import asyncio
import os
import uuid
import time

import httpx

from .ai import DomainExecution, answer, current_execution
from .dispatch import OperationError, dispatch


executions: dict[str, DomainExecution] = {}
job_executions: dict[str, DomainExecution] = {}


async def submit(operation, arguments, athlete, person):
    arguments = {key: value for key, value in arguments.items() if key not in {'_access', '_person_pk', '_if_job_id'}}
    if not person:
        raise OperationError(401, "invalid_principal", "Verified acting Person required")
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(
            os.environ["IF_API_URL"].rstrip("/") + "/v1/jobs",
            headers={'X-Person-Pk': person, 'X-Athlete-Pk': athlete},
            json={"conversation_id": f"powerlifting:{athlete}:{uuid.uuid4().hex}", "kind": "domain", "payload": {"domain": operation.domain, "operation": operation.name, "arguments": arguments, "athlete": athlete}},
        )
        if response.is_error:
            raise OperationError(response.status_code, "busy" if response.status_code == 429 else "execution_failed", response.text)
        job = response.json()
    return {"job_id": job["job_id"], "status": job["status"]}


async def start(operation, arguments, athlete, job_id):
    for key, previous in list(executions.items()):
        if previous.deadline < time.monotonic() and previous.future.done():
            executions.pop(key, None)
            job_executions.pop(previous.job_id, None)
    person = arguments.get("_person_pk")
    if not isinstance(person, str) or not person:
        raise OperationError(401, "invalid_principal", "Verified acting Person required")
    execution = DomainExecution(job_id=job_id, athlete=athlete, person=person, operation=operation.name)
    executions[execution.execution_id] = execution
    job_executions[job_id] = execution
    token = current_execution.set(execution)
    try:
        execution.future = asyncio.create_task(asyncio.to_thread(dispatch, operation, arguments))
    finally:
        current_execution.reset(token)
    return await poll(execution)


async def poll(execution):
    for _ in range(200):
        if execution.future.done():
            executions.pop(execution.execution_id, None)
            job_executions.pop(execution.job_id, None)
            result = execution.future.result()
            if execution.error:
                raise OperationError(409, "uncertain", execution.error)
            return {"status": "succeeded", "result": result}
        if execution.challenge and not execution.ready.is_set():
            return {"status": "needs_inference", "execution_id": execution.execution_id, **execution.challenge}
        await asyncio.sleep(0.01)
    return {"status": "running", "execution_id": execution.execution_id}


async def resume(execution_id, job_id, athlete, challenge_id=None, content=None):
    execution = executions.get(execution_id)
    if execution is None or execution.job_id != job_id or execution.athlete != athlete:
        raise OperationError(409, "uncertain", "Domain execution unavailable; do not replay mutations")
    if challenge_id:
        answer(execution, challenge_id, content)
    return await poll(execution)


async def dispatch_nested(operation, arguments, athlete, job_id):
    execution = job_executions.get(job_id)
    if execution is None:
        if operation.execution != "ai":
            return await asyncio.to_thread(dispatch, operation, arguments)
        raise OperationError(409, "uncertain", "Active domain execution unavailable; do not replay mutations")
    if execution.athlete != athlete or execution.future is None or execution.future.done():
        raise OperationError(409, "uncertain", "Active domain execution unavailable; do not replay mutations")
    token = current_execution.set(execution)
    try:
        return await asyncio.to_thread(dispatch, operation, arguments)
    finally:
        current_execution.reset(token)
