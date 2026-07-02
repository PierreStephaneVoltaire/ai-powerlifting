"""AI-powered evaluation of training templates.

Analyzes a template against an athlete's profile, competition timeline,
and current metrics to produce a recommendation stance and suggestions.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai_config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from prompts.loader import load_system_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("template_evaluate_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_template_evaluation",
        "description": "Report the evaluation of a training template",
        "parameters": {
            "type": "object",
            "properties": {
                "stance": {"type": "string", "enum": ["continue", "monitor", "adjust", "critical"]},
                "summary": {"type": "string"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "week": {"type": ["number", "null"]},
                            "phase": {"type": ["string", "null"]},
                            "exercise": {"type": ["string", "null"]},
                            "rationale": {"type": "string"}
                        },
                        "required": ["type", "rationale"]
                    }
                },
                "projected_readiness_at_comp": {"type": "number"},
                "data_citations": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["stance", "summary", "strengths", "weaknesses", "suggestions", "projected_readiness_at_comp"]
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

async def generate_template_evaluate_report(
    template: dict[str, Any],
    athlete_context: dict[str, Any]
) -> dict[str, Any]:
    """Call the LLM to evaluate a template against athlete context."""
    user_msg = json.dumps({
        "template": template,
        "athlete_context": athlete_context
    }, indent=2)

    logger.info(f"[TemplateEvaluateAI] model={ANALYSIS_MODEL} payload_chars={len(user_msg)}")

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
                    "tool_choice": {"type": "function", "function": {"name": "report_template_evaluation"}},
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
            raise ValueError("No tool calls in LLM response")

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        return _sanitize_floats(json.loads(args_str))

    except Exception as e:
        logger.error(f"[TemplateEvaluateAI] evaluation failed: {e}")
        return {
            "stance": "monitor",
            "summary": f"AI evaluation failed: {e}",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "projected_readiness_at_comp": 50
        }
