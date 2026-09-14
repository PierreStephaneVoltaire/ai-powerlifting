from __future__ import annotations

import json
import logging
import math
from typing import Any

from prompts.loader import load_system_prompt
from services.ai import completion


logger = logging.getLogger(__name__)
_SYSTEM_PROMPT = load_system_prompt("import_parse_system")
_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_parse_result",
        "description": "Report the structured parse result of a training program",
        "parameters": {
            "type": "object",
            "properties": {
                "phases": {"type": "array", "items": {"type": "object"}},
                "sessions": {"type": "array", "items": {"type": "object"}},
                "warnings": {"type": "array", "items": {"type": "object"}},
                "parse_notes": {"type": "string"},
            },
            "required": ["phases", "sessions", "warnings", "parse_notes"],
        },
    },
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


async def generate_import_parse_report(file_content, file_name, classification, athlete_context=None):
    user_message = json.dumps({
        "file_content": file_content,
        "file_name": file_name,
        "classification": classification,
        "athlete_context": athlete_context or {},
    }, indent=2, default=str)
    try:
        response = await completion({
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "tools": [_TOOL_SCHEMA],
            "tool_choice": {"type": "function", "function": {"name": "report_parse_result"}},
        })
        response.raise_for_status()
        choices = response.json().get("choices", [])
        if not choices:
            raise ValueError("No choices in native response")
        message = choices[0].get("message", {})
        calls = message.get("tool_calls", [])
        if calls:
            raw = calls[0].get("function", {}).get("arguments", "{}")
            return _sanitize(json.loads(raw))
        content = (message.get("content") or "").strip()
        if content.startswith("{"):
            return _sanitize(json.loads(content))
        raise ValueError("No tool call or JSON content in native response")
    except Exception as exc:
        logger.error("Import parsing failed: %s", exc)
        return {
            "phases": [],
            "sessions": [],
            "warnings": [{"type": "error", "message": str(exc)}],
            "parse_notes": f"AI parse failed: {exc}",
        }
