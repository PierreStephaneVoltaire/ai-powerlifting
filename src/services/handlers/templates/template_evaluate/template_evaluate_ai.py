"""AI-powered review of a training template's design."""
from __future__ import annotations
from services.ai import completion

import json
from decimal import Decimal
import logging
from typing import Any

from services.handlers.program.export_program_markdown.prompt_context import FORMULA_REFERENCE
from services.lib.prompts.loader import load_system_prompt

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
                "data_citations": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["stance", "summary", "strengths", "weaknesses", "suggestions"]
        }
    }
}

def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


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
    athlete_context: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    program_context: str = "",
) -> dict[str, Any]:
    user_msg = json.dumps({
        "program_context": program_context or "Not provided.",
        "template": template,
        "metrics": metrics or {},
        "athlete_context": athlete_context,
        "formula_reference": FORMULA_REFERENCE,
    }, indent=2, default=_json_default)

    logger.info("[TemplateEvaluateAI] payload_chars=%s", len(user_msg))

    resp = await completion({'messages': [{'role': 'system', 'content': _SYSTEM_PROMPT}, {'role': 'user', 'content': user_msg}], 'tools': [_TOOL_SCHEMA], 'tool_choice': {'type': 'function', 'function': {'name': 'report_template_evaluation'}}})
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

    return _sanitize_floats(json.loads(tool_calls[0].get("function", {}).get("arguments", "{}")))
