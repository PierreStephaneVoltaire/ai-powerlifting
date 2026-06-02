"""AI-powered classification of training program spreadsheets.

Used when deterministic heuristics cannot confidently distinguish between
a Template (date-free) and a Session Import (dated).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import LLM_BASE_URL, OPENROUTER_API_KEY, IMPORT_FAST_MODEL
from prompts.loader import load_system_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("import_classify_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_classification",
        "description": "Report the classification of a training program file",
        "parameters": {
            "type": "object",
            "properties": {
                "classification": {"type": "string", "enum": ["template", "session_import", "ambiguous"]},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
                "ambiguity_reason": {"type": "string"}
            },
            "required": ["classification", "confidence", "reasoning"]
        }
    }
}

async def generate_classification_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the LLM to classify rows from a spreadsheet."""
    sample = rows[:30]
    user_msg = json.dumps({"rows_sample": sample}, indent=2, default=str)

    logger.info(f"[ImportClassifyAI] model={IMPORT_FAST_MODEL} payload_chars={len(user_msg)}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": IMPORT_FAST_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "tools": [_TOOL_SCHEMA],
                    "tool_choice": {"type": "function", "function": {"name": "report_classification"}},
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
                return json.loads(content)
            raise ValueError("No tool calls in LLM response")

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        return json.loads(args_str)

    except Exception as e:
        logger.error(f"[ImportClassifyAI] classification failed: {e}")
        return {
            "classification": "ambiguous",
            "confidence": 0.0,
            "reasoning": f"AI classification failed: {e}",
            "ambiguity_reason": str(e)
        }
