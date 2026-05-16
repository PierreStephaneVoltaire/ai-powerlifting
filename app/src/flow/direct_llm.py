"""Direct OpenRouter chat loop with MCP-backed tool calls."""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

import httpx

from channels.status import StatusType, send_status
from config import OPENROUTER_BASE_URL, OPENROUTER_HEADERS

logger = logging.getLogger(__name__)

ToolDispatcher = Callable[[str, dict[str, Any]], Awaitable[str]]


def _normalize_tool_call(tool_call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    call_id = str(tool_call.get("id") or "")
    fn = tool_call.get("function") or {}
    name = str(fn.get("name") or tool_call.get("name") or "")
    raw_args = fn.get("arguments") if "arguments" in fn else tool_call.get("arguments", "{}")
    if isinstance(raw_args, dict):
        args = raw_args
    else:
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError:
            args = {"_raw_arguments": raw_args}
    return call_id, name, args


async def call_openrouter_chat(
    *,
    http_client: httpx.AsyncClient,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_dispatcher: ToolDispatcher | None = None,
    max_tool_rounds: int = 8,
) -> str:
    await send_status(
        StatusType.MODEL_SELECTED,
        "Model Selected",
        model,
    )

    working_messages = list(messages)
    url = f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"

    for round_index in range(max_tool_rounds + 1):
        payload: dict[str, Any] = {
            "model": model,
            "messages": working_messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await http_client.post(url, headers=OPENROUTER_HEADERS, json=payload, timeout=180.0)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        content = message.get("content") or ""

        if not tool_calls:
            return content if isinstance(content, str) else str(content)

        if not tool_dispatcher:
            logger.warning("Model requested tool calls, but no tool dispatcher is configured")
            return content if isinstance(content, str) else str(content)

        if round_index >= max_tool_rounds:
            logger.warning("Tool loop hit max rounds (%s)", max_tool_rounds)
            return content if isinstance(content, str) else str(content)

        working_messages.append(
            {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            }
        )

        for tool_call in tool_calls:
            call_id, name, args = _normalize_tool_call(tool_call)
            await send_status(StatusType.TOOL_STARTED, "Tool Started", name)
            try:
                result = await tool_dispatcher(name, args)
                await send_status(StatusType.TOOL_COMPLETED, "Tool Completed", name)
            except Exception as exc:
                logger.exception("Tool call failed: %s", name)
                await send_status(StatusType.TOOL_FAILED, "Tool Failed", f"{name}: {exc}")
                result = f"ERROR: {type(exc).__name__}: {exc}"

            working_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": result,
                }
            )

    return ""

