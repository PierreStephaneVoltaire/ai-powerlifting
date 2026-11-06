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

from services.lib import prompt_cache


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
JUDGE_INSTRUCTION = "Use a fresh Luna Specialist child with low reasoning effort to answer these messages. Return its structured result using domain_resume. Do not submit another IF job."
JUDGE_CONFIDENCE = 0.8
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "match_id": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["match_id", "confidence"],
    "additionalProperties": False,
}


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


def _judge_messages(request: dict[str, Any], candidates: list[prompt_cache.Candidate]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Decide whether a previously generated answer can be reused for a new request. Reuse only when the new request asks for the same thing about the same data, so the cached answer would be just as correct and complete. Any difference in the underlying numbers, dates, sessions, or requested output means no match. Return match_id null when nothing qualifies."},
        {"role": "user", "content": json.dumps({
            "new_request": request,
            "candidates": [{"id": candidate.id, "similarity": round(candidate.similarity, 3), "request": candidate.request} for candidate in candidates],
        }, default=str)},
    ]


async def _reusable(execution: DomainExecution, request: dict[str, Any]) -> dict[str, Any] | None:
    hit = await asyncio.to_thread(prompt_cache.exact, execution.athlete, execution.operation, request)
    if hit is not None:
        return hit
    candidates = await asyncio.to_thread(prompt_cache.similar, execution.athlete, execution.operation, request)
    if not candidates:
        return None
    judged = await _delegate(
        execution,
        _judge_messages(request, candidates),
        [],
        {"type": "json_schema", "json_schema": {"name": "prompt_cache_match", "schema": JUDGE_SCHEMA}},
        JUDGE_INSTRUCTION,
    )
    verdict = json.loads(judged["choices"][0]["message"]["content"])
    if verdict["confidence"] < JUDGE_CONFIDENCE:
        return None
    return next((candidate.response for candidate in candidates if candidate.id == verdict["match_id"]), None)


async def completion(payload: dict[str, Any]) -> httpx.Response:
    execution = current_execution.get()
    if execution is None:
        raise RuntimeError("Domain AI requires an active IF execution; direct model calls are disabled")
    request = prompt_cache.cache_request(payload)
    response = await _reusable(execution, request)
    if response is None:
        response = await _delegate(execution, payload.get("messages", []), payload.get("tools", []), payload.get("response_format"), SPECIALIST_INSTRUCTION)
        await asyncio.to_thread(prompt_cache.remember, execution.athlete, execution.operation, request, response)
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
