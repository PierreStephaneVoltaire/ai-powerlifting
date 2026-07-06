"""AI-powered extraction of structured training data from spreadsheet content.

Supports both Templates (date-free) and Session Imports (dated logs).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai_config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from prompts.loader import load_system_prompt

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
                "parse_notes": {"type": "string"}
            },
            "required": ["phases", "sessions", "warnings", "parse_notes"]
        }
    }
}

def _sanitize_floats(obj: Any) -> Any:
    import math
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_floats(v) for v in obj]
    return obj

async def generate_import_parse_report(
    file_content: str,
    file_name: str,
    classification: str,
    athlete_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call the LLM to extract structured data from file content."""
    user_msg = json.dumps({
        "file_content": file_content,
        "file_name": file_name,
        "classification": classification,
        "athlete_context": athlete_context or {}
    }, indent=2, default=str)

    logger.info(f"[ImportParseAI] model={ANALYSIS_MODEL} payload_chars={len(user_msg)}")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ANALYSIS_MODEL,
                    "thinking": {"type": "enabled", "budget_tokens": ANALYSIS_MODEL_THINKING_BUDGET},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "tools": [_TOOL_SCHEMA],
                    "tool_choice": {"type": "function", "function": {"name": "report_parse_result"}},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices in LLM response")

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            content = message.get("content", "").strip()
            if content.startswith("{"):
                return _sanitize_floats(json.loads(content))
            raise ValueError("No tool calls or valid JSON content in LLM response")

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        return _sanitize_floats(json.loads(args_str))

    except Exception as e:
        logger.error(f"[ImportParseAI] extraction failed: {e}")
        return {
            "phases": [],
            "sessions": [],
            "warnings": [{"type": "error", "message": str(e)}],
            "parse_notes": f"AI parse failed: {e}"
        }
