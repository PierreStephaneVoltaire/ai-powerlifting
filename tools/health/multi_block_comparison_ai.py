"""LLM-powered comparison across multiple powerlifting training blocks."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are an objective sports scientist comparing multiple powerlifting training
blocks for the same athlete.

Use the supplied block analysis data. Do not invent sessions, lifts, maxes,
bodyweight trends, or competition outcomes. Treat correlations as low sample
signals unless multiple blocks point in the same direction. If data is sparse,
say exactly what is missing and keep the conclusion conservative.

The athlete wants to know:
- which blocks looked similar or different,
- what training seemed to work and what did not,
- lift-specific patterns for squat, bench, and deadlift,
- multi-block exercise ROI signals,
- volume dose response, including likely minimal effective and maximum
  tolerable volume ranges when the data supports it,
- whether bodyweight or training-day count related to max increases,
- which block provided the best value,
- whether projections matched competition results,
- which lift lagged at competitions,
- when progress or fatigue started to deteriorate,
- factual data limits only. Do not recommend next experiments or programming changes.

Prefer concrete references to block names, dates, lifts, volume, INOL, fatigue,
ACWR, compliance, bodyweight, and competition results. Avoid generic coaching
advice.
"""


_INSIGHT_OBJECT = {
    "type": "object",
    "properties": {
        "finding": {"type": "string"},
        "evidence": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["finding", "evidence", "confidence"],
}


_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_multi_block_comparison",
        "description": "Return a conservative multi-block powerlifting analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "overall_summary": {"type": "string"},
                "similarities": {"type": "array", "items": _INSIGHT_OBJECT},
                "differences": {"type": "array", "items": _INSIGHT_OBJECT},
                "what_works": {"type": "array", "items": _INSIGHT_OBJECT},
                "what_does_not_work": {"type": "array", "items": _INSIGHT_OBJECT},
                "lift_specific_insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lift": {"type": "string", "enum": ["squat", "bench", "deadlift", "total"]},
                            "finding": {"type": "string"},
                            "evidence": {"type": "string"},
                            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["lift", "finding", "evidence", "confidence"],
                    },
                },
                "multi_block_exercise_roi": {"type": "array", "items": _INSIGHT_OBJECT},
                "volume_dose_response": {"type": "array", "items": _INSIGHT_OBJECT},
                "bodyweight_relationships": {"type": "array", "items": _INSIGHT_OBJECT},
                "training_day_frequency": {"type": "array", "items": _INSIGHT_OBJECT},
                "best_value_blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "block": {"type": "string"},
                            "reason": {"type": "string"},
                            "tradeoff": {"type": "string"},
                            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["block", "reason", "tradeoff", "confidence"],
                    },
                },
                "projection_accuracy": {"type": "array", "items": _INSIGHT_OBJECT},
                "progress_dropoff_points": {"type": "array", "items": _INSIGHT_OBJECT},
                "fatigue_patterns": {"type": "array", "items": _INSIGHT_OBJECT},
                "data_limits": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "overall_summary",
                "similarities",
                "differences",
                "what_works",
                "what_does_not_work",
                "lift_specific_insights",
                "multi_block_exercise_roi",
                "volume_dose_response",
                "bodyweight_relationships",
                "training_day_frequency",
                "best_value_blocks",
                "projection_accuracy",
                "progress_dropoff_points",
                "fatigue_patterns",
                "data_limits",
            ],
        },
    },
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _default_report(reason: str) -> dict[str, Any]:
    return {
        "overall_summary": reason,
        "similarities": [],
        "differences": [],
        "what_works": [],
        "what_does_not_work": [],
        "lift_specific_insights": [],
        "multi_block_exercise_roi": [],
        "volume_dose_response": [],
        "bodyweight_relationships": [],
        "training_day_frequency": [],
        "best_value_blocks": [],
        "projection_accuracy": [],
        "progress_dropoff_points": [],
        "fatigue_patterns": [],
        "data_limits": [reason],
        "insufficient_data": True,
        "insufficient_data_reason": reason,
    }


def _normalize_report(args: dict[str, Any]) -> dict[str, Any]:
    report = _default_report("")
    report["insufficient_data"] = False
    report["insufficient_data_reason"] = ""
    for key in [
        "overall_summary",
        "similarities",
        "differences",
        "what_works",
        "what_does_not_work",
        "lift_specific_insights",
        "multi_block_exercise_roi",
        "volume_dose_response",
        "bodyweight_relationships",
        "training_day_frequency",
        "best_value_blocks",
        "projection_accuracy",
        "progress_dropoff_points",
        "fatigue_patterns",
        "data_limits",
    ]:
        if key == "overall_summary":
            report[key] = args.get(key, "") if isinstance(args.get(key), str) else ""
        else:
            report[key] = args.get(key, []) if isinstance(args.get(key), list) else []
    return report


async def generate_multi_block_comparison_report(payload: dict[str, Any]) -> dict[str, Any]:
    blocks = payload.get("blocks") if isinstance(payload, dict) else None
    if not isinstance(blocks, list) or len(blocks) < 1:
        return _default_report("No block analysis payload was supplied.")

    user_msg = json.dumps(_sanitize(payload), indent=2, default=str)
    logger.info("[MultiBlockComparisonAI] model=%s payload_chars=%s", ANALYSIS_MODEL, len(user_msg))

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
                    "tool_choice": "required",
                },
            )
            if resp.status_code >= 400:
                logger.error("[MultiBlockComparisonAI] HTTP %s: %s", resp.status_code, resp.text[:2000])
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices in LLM response")
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            raise ValueError("No tool calls in LLM response")

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        args = json.loads(args_str)
        return _normalize_report(args if isinstance(args, dict) else {})
    except Exception as exc:
        logger.error("[MultiBlockComparisonAI] generation failed: %s", exc)
        return _default_report(f"AI multi-block comparison failed: {exc}")
