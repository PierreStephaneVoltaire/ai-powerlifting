import asyncio
import os
import uuid
import time
import json

from .generations import GenerationStore, REPORTS, fingerprint, report_source

import httpx

from .ai import DomainExecution, answer, current_execution
from .dispatch import OperationError, dispatch


executions: dict[str, DomainExecution] = {}
job_executions: dict[str, DomainExecution] = {}


async def submit(operation, arguments, athlete, person):
    generation = None
    store = None
    if operation.name in REPORTS:
        source = await report_source(arguments, athlete, operation.name)
        generation_id = fingerprint(operation.name, arguments, source)
        if source:
            arguments = {**arguments, "_report_source": source}
        store = GenerationStore(athlete)
        if arguments.get("cache_only"):
            record = await asyncio.to_thread(store.get, generation_id)
            if record and record["status"] == "succeeded":
                return await asyncio.to_thread(store.result, record)
            return {"cached": False, "cache_miss": True, "generation_id": generation_id, "status": (record or {}).get("status", "missing")}
        generation, created = await asyncio.to_thread(store.reserve, generation_id, operation.name, person or athlete, bool(arguments.get("refresh")))
        if not created:
            if generation["status"] == "succeeded":
                result = await asyncio.to_thread(store.result, generation)
                return {**result, "cached": True} if isinstance(result, dict) else result
            return {"generation_id": generation_id, "job_id": generation.get("job_id"), "status": generation["status"]}
    if generation:
        arguments = {**arguments, "refresh": True, "cache_only": False}
    key = f"{generation['generation_id']}:{generation['attempt']}" if generation else uuid.uuid4().hex
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(
                os.environ["IF_API_URL"].rstrip("/") + "/v1/jobs",
                headers={"X-Internal-Token": os.environ["INTERNAL_API_TOKEN"], "X-Person-Pk": person or athlete},
                json={"conversation_id": f"powerlifting:{athlete}:{key}", "kind": "domain", "payload": {"domain": operation.domain, "operation": operation.name, "arguments": arguments, "athlete": athlete, **({"generation_id": generation["generation_id"], "generation_attempt": int(generation["attempt"])} if generation else {})}, "idempotency_key": key},
            )
            if response.is_error:
                raise OperationError(response.status_code, "busy" if response.status_code == 429 else "execution_failed", response.text)
            job = response.json()
        if generation:
            await asyncio.to_thread(store.update, generation["generation_id"], expected_attempt=generation["attempt"], job_id=job["job_id"])
        return {"job_id": job["job_id"], "status": job["status"], **({"generation_id": generation["generation_id"]} if generation else {})}
    except Exception as exc:
        if generation:
            await asyncio.to_thread(store.update, generation["generation_id"], expected_attempt=generation["attempt"], status="failed" if isinstance(exc, OperationError) else "uncertain", error=str(exc))
        raise


async def start(operation, arguments, athlete, job_id):
    for key, previous in list(executions.items()):
        if previous.deadline < time.monotonic() and previous.future.done():
            executions.pop(key, None)
            job_executions.pop(previous.job_id, None)
    if operation.name in REPORTS and not arguments.get("_generation_id"):
        store = GenerationStore(athlete)
        source = await report_source(arguments, athlete, operation.name)
        generation_id = fingerprint(operation.name, arguments, source)
        if source:
            arguments = {**arguments, "_report_source": source}
        if arguments.get("cache_only"):
            record = await asyncio.to_thread(store.get, generation_id)
            result = await asyncio.to_thread(store.result, record) if record and record["status"] == "succeeded" else {"cached": False, "cache_miss": True}
            return {"status": "succeeded", "result": result}
        record, created = await asyncio.to_thread(store.reserve, generation_id, operation.name, arguments.get("_person_pk") or athlete, bool(arguments.get("refresh")))
        if not created:
            result = await asyncio.to_thread(store.result, record) if record["status"] == "succeeded" else {"generation_id": generation_id, "status": record["status"]}
            return {"status": "succeeded", "result": result}
        arguments = {**arguments, "_generation_id": generation_id, "_generation_attempt": int(record["attempt"]), "refresh": True}
        await asyncio.to_thread(store.update, generation_id, expected_attempt=record["attempt"], job_id=job_id)
    execution = DomainExecution(job_id=job_id, athlete=athlete)
    execution.generation_id = arguments.get("_generation_id")
    execution.generation_attempt = arguments.get("_generation_attempt")
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
            try:
                result = execution.future.result()
                if execution.error:
                    raise OperationError(409, "uncertain", execution.error)
            except Exception as exc:
                if getattr(execution, "generation_id", None):
                    await asyncio.to_thread(GenerationStore(execution.athlete).update, execution.generation_id, expected_attempt=execution.generation_attempt, status="failed", error=str(exc))
                raise
            if getattr(execution, "generation_id", None):
                await asyncio.to_thread(GenerationStore(execution.athlete).complete, execution.generation_id, result, execution.generation_attempt)
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
