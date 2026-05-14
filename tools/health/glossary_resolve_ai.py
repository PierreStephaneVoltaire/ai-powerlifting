"""AI-powered resolution of exercise names to the canonical glossary.

Handles abbreviations, common nicknames, and shorthand (e.g. "RDL" -> "Romanian Deadlift").
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import LLM_BASE_URL, OPENROUTER_API_KEY, IMPORT_FAST_MODEL
from prompts.loader import load_system_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("glossary_resolve_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_glossary_resolution",
        "description": "Report the resolution of exercise names to glossary IDs",
        "parameters": {
            "type": "object",
            "properties": {
                "resolutions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "input": {"type": "string"},
                            "matched_id": {"type": ["string", "null"]},
                            "confidence": {"type": "number"},
                            "method": {"type": "string", "enum": ["exact", "abbreviation", "nickname", "no_match"]},
                            "suggested_new_entry": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "category": {"type": "string"},
                                    "equipment": {"type": "string"}
                                }
                            }
                        },
                        "required": ["input", "matched_id", "confidence", "method"]
                    }
                }
            },
            "required": ["resolutions"]
        }
    }
}

async def generate_glossary_resolve_report(
    exercise_names_from_file: list[str],
    existing_glossary: list[dict[str, Any]]
) -> dict[str, Any]:
    """Call the LLM to resolve exercise names to glossary entries."""
    user_msg = json.dumps({
        "exercise_names_from_file": exercise_names_from_file,
        "existing_glossary": [
            {"id": ex.get("id"), "name": ex.get("name")} 
            for ex in existing_glossary
        ]
    }, indent=2)

    logger.info(f"[GlossaryResolveAI] model={IMPORT_FAST_MODEL} payload_chars={len(user_msg)}")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
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
                    "tool_choice": {"type": "function", "function": {"name": "report_glossary_resolution"}},
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
        logger.error(f"[GlossaryResolveAI] resolution failed: {e}")
        return {
            "resolutions": [
                {
                    "input": name,
                    "matched_id": None,
                    "confidence": 0.0,
                    "method": "no_match"
                }
                for name in exercise_names_from_file
            ]
        }
