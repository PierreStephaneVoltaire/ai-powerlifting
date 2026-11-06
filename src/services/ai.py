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
JUDGE_INSTRUCTION = "Use a fresh powerlifting_coach Specialist child on the Luna model with low reasoning effort to answer these messages; it must search the prompt cache tool as instructed. Return its structured result using domain_resume. Do not submit another IF job."
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


def _judge_messages(request: dict[str, Any], collection: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": (
            f"Decide whether a saved answer can be reused for the new request below. Search the prompt cache with the {prompt_cache.SEARCH_TOOL} tool "
            f"using collection_name \"{collection}\" and a query describing the new request; search again with different wording if useful. "
            "Each result holds a saved request and its entry_id in metadata. Reuse only when a saved request asks for the same thing about the same data, "
            "so its answer would be just as correct and complete. Any difference in the underlying numbers, dates, sessions, or requested output means no match. "
            "Return the matching entry_id as match_id, or null when nothing qualifies."
        )},
        {"role": "user", "content": json.dumps({"new_request": request}, default=str)},
    ]


async def _reusable(execution: DomainExecution, request: dict[str, Any]) -> dict[str, Any] | None:
    hit = await asyncio.to_thread(prompt_cache.exact, execution.athlete, execution.operation, request)
    if hit is not None:
        return hit
    if not await asyncio.to_thread(prompt_cache.has_entries, execution.athlete, execution.operation):
        return None
    judged = await _delegate(
        execution,
        _judge_messages(request, prompt_cache.collection(execution.athlete, execution.operation)),
        [],
        {"type": "json_schema", "json_schema": {"name": "prompt_cache_match", "schema": JUDGE_SCHEMA}},
        JUDGE_INSTRUCTION,
    )
    verdict = json.loads(judged["choices"][0]["message"]["content"])
    if verdict["confidence"] < JUDGE_CONFIDENCE or not verdict["match_id"]:
        return None
    return await asyncio.to_thread(prompt_cache.entry, execution.athlete, execution.operation, verdict["match_id"])


async def completion(payload: dict[str, Any]) -> httpx.Response:
    execution = current_execution.get()
    if execution is None:
        raise RuntimeError("Domain AI requires an active IF execution; direct model calls are disabled")
    request = prompt_cache.cache_request(payload)
    response = await _reusable(execution, request)
    if response is None:
        response = await _delegate(execution, payload.get("messages", []), payload.get("tools", []), payload.get("response_format"), SPECIALIST_INSTRUCTION)
        await prompt_cache.remember(execution.athlete, execution.operation, request, response)
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
