from __future__ import annotations

import json
import logging

from services.runtime.ai import completion
from services.runtime.prompts.loader import load_system_prompt, render_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("lift_transfer_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_lift_transfer",
        "description": "Estimate how much an exercise transfers to each competition lift",
        "parameters": {
            "type": "object",
            "properties": {
                "squat": {"type": "number", "minimum": 0, "maximum": 1, "description": "Transfer to the competition squat 0.0-1.0"},
                "bench": {"type": "number", "minimum": 0, "maximum": 1, "description": "Transfer to the competition bench press 0.0-1.0"},
                "deadlift": {"type": "number", "minimum": 0, "maximum": 1, "description": "Transfer to the competition deadlift 0.0-1.0"},
                "reasoning": {"type": "string", "description": "Brief explanation of the estimates"},
            },
            "required": ["squat", "bench", "deadlift", "reasoning"],
        },
    },
}


def _clamp(value, step: float = 0.05) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = 0.0
    return max(0.0, min(1.0, round(round(raw / step) * step, 2)))


async def estimate_lift_transfer(exercise: dict) -> dict:
    resp = await completion({
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": render_prompt("lift_transfer_user", exercise=exercise)},
        ],
        "tools": [_TOOL_SCHEMA],
        "tool_choice": {"type": "function", "function": {"name": "estimate_lift_transfer"}},
    })
    resp.raise_for_status()
    choices = resp.json().get("choices", [])
    tool_calls = choices[0].get("message", {}).get("tool_calls", []) if choices else []
    if not tool_calls:
        raise ValueError("The lift transfer estimate returned no result")
    args = json.loads(tool_calls[0].get("function", {}).get("arguments", "{}"))
    return {
        "squat": _clamp(args.get("squat")),
        "bench": _clamp(args.get("bench")),
        "deadlift": _clamp(args.get("deadlift")),
        "source": "ai",
        "reasoning": str(args.get("reasoning", "")).strip(),
    }
