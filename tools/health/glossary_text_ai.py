"""Cheap AI prose generation for exercise glossary entries."""
from __future__ import annotations

import json
import logging
import re

import httpx

from config import GLOSSARY_TEXT_MODEL, LLM_BASE_URL, OPENROUTER_API_KEY
from prompts.loader import load_system_prompt, render_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("glossary_text_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_glossary_text",
        "description": "Generate concise exercise glossary prose",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What the exercise is, in 1-2 concise sentences.",
                },
                "how_to_perform": {
                    "type": "string",
                    "description": "How to perform the exercise, in 3-5 concise steps.",
                },
                "why_do_it": {
                    "type": "string",
                    "description": "Why the exercise is useful for powerlifting training.",
                },
            },
            "required": ["description", "how_to_perform", "why_do_it"],
        },
    },
}


def _compact_text(value: object, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_result(payload: dict) -> dict:
    return {
        "description": _compact_text(payload.get("description")),
        "how_to_perform": _compact_text(payload.get("how_to_perform"), 1200),
        "why_do_it": _compact_text(payload.get("why_do_it")),
    }


def _build_user_message(
    exercise: dict,
    lift_profiles: list[dict] | None = None,
) -> str:
    return render_prompt(
        "glossary_text_user",
        exercise=exercise,
        lift_profiles=lift_profiles or [],
    )


async def generate_glossary_text(
    exercise: dict,
    lift_profiles: list[dict] | None = None,
) -> dict:
    """Generate short editable glossary text for one exercise."""
    user_msg = _build_user_message(exercise, lift_profiles=lift_profiles)
    logger.info("[GlossaryTextAI] model=%s payload_chars=%s", GLOSSARY_TEXT_MODEL, len(user_msg))

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GLOSSARY_TEXT_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens": 700,
                "tools": [_TOOL_SCHEMA],
                "tool_choice": {"type": "function", "function": {"name": "generate_glossary_text"}},
            },
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Glossary text generation returned no choices")

    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        parsed = json.loads(args_str)
        if not isinstance(parsed, dict):
            raise ValueError("Glossary text generation returned non-object tool arguments")
        return _normalize_result(parsed)

    parsed = _extract_json_object(str(message.get("content") or ""))
    result = _normalize_result(parsed)
    if not any(result.values()):
        raise ValueError("Glossary text generation returned empty content")
    return result
