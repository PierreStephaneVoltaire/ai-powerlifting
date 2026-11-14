import asyncio
import contextvars
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from jsonschema import Draft202012Validator

from services.runtime import llm_log, prompt_cache


current_execution = contextvars.ContextVar("domain_execution", default=None)


@dataclass
class DomainExecution:
    job_id: str
    athlete: str
    person: str = ""
    operation: str = ""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    challenge: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    ready: threading.Event = field(default_factory=threading.Event)
    future: asyncio.Task | None = None
    error: str | None = None
    deadline: float = field(default_factory=lambda: time.monotonic() + 900)


SPECIALIST_INSTRUCTION = "Use a native Specialist child to answer these messages. Return its structured result using domain_resume. Do not submit another IF job."
async def _delegate(execution: DomainExecution, messages: list, tools: list, response_format: Any, instruction: str) -> dict[str, Any]:
    execution.ready.clear()
    execution.response = None
    execution.challenge = {"challenge_id": uuid.uuid4().hex, "messages": messages, "tools": tools, "response_format": response_format, "instruction": instruction}
    remaining = max(0, execution.deadline - time.monotonic())
    if not await asyncio.to_thread(execution.ready.wait, remaining):
        execution.error = "Native delegation response timed out; reconcile this operation before retrying"
        raise TimeoutError(execution.error)
    response = execution.response
    execution.challenge = None
    if response is None:
        execution.error = "Domain inference was cancelled"
        raise RuntimeError(execution.error)
    return response


async def completion(payload: dict[str, Any]) -> httpx.Response:
    execution = current_execution.get()
    if execution is None:
        raise RuntimeError("Domain AI requires an active IF execution; direct model calls are disabled")
    request = prompt_cache.cache_request(payload)
    started = time.monotonic()
    response = await asyncio.to_thread(prompt_cache.exact, execution.athlete, execution.operation, request)
    cache_layer = "exact" if response is not None else "none"
    if response is None:
        response = await _delegate(execution, payload.get("messages", []), payload.get("tools", []), payload.get("response_format"), SPECIALIST_INSTRUCTION)
        await asyncio.to_thread(prompt_cache.remember, execution.athlete, execution.operation, request, response)
    llm_log.emit(
        "ai_request",
        operation=execution.operation,
        athlete=execution.athlete,
        person=execution.person,
        job_id=execution.job_id,
        cache_layer=cache_layer,
        request_hash=prompt_cache.request_hash(request),
        latency_ms=round((time.monotonic() - started) * 1000),
        request=request,
        response=response,
    )
    return httpx.Response(200, json=response, request=httpx.Request("POST", "http://native-delegation"))


def answer(execution: DomainExecution, challenge_id: str, content: Any):
    challenge = execution.challenge
    if not challenge or challenge["challenge_id"] != challenge_id or execution.ready.is_set():
        raise ValueError("Challenge is stale or already answered")
    text = content if isinstance(content, str) else json.dumps(content)
    tools = challenge.get("tools") or []
    schema = tools[0]["function"].get("parameters") if tools else (challenge.get("response_format") or {}).get("json_schema", {}).get("schema")
    if schema:
        Draft202012Validator(schema).validate(json.loads(text))
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if tools:
        message["tool_calls"] = [{"id": uuid.uuid4().hex, "type": "function", "function": {"name": tools[0]["function"]["name"], "arguments": text}}]
    execution.response = {"choices": [{"message": message, "finish_reason": "tool_calls" if tools else "stop"}]}
    execution.ready.set()
