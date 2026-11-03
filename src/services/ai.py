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


async def completion(payload: dict[str, Any]) -> httpx.Response:
    execution = current_execution.get()
    if execution is None:
        raise RuntimeError("Domain AI requires an active IF execution; direct model calls are disabled")
    execution.ready.clear()
    execution.response = None
    execution.challenge = {"challenge_id": uuid.uuid4().hex, "messages": payload.get("messages", []), "tools": payload.get("tools", []), "response_format": payload.get("response_format"), "instruction": "Use a native Specialist child to answer these messages. Return its structured result using domain_resume. Do not submit another IF job."}
    remaining = max(0, execution.deadline - time.monotonic())
    if not await asyncio.to_thread(execution.ready.wait, remaining):
        execution.error = "Native delegation response timed out; reconcile this operation before retrying"
        raise TimeoutError(execution.error)
    response = execution.response
    execution.challenge = None
    if response is None:
        execution.error = "Domain inference was cancelled"
        raise RuntimeError(execution.error)
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
