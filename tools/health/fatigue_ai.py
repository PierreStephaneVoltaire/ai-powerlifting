"""LLM-based 4-dimensional fatigue profile estimation for exercises.

Uses OpenRouter to call an extended-thinking model with tool calling to get structured
fatigue profile estimates (axial, neural, peripheral, systemic).
"""
from __future__ import annotations

import json
import logging

import httpx

from config import (
    ESTIMATE_MODEL,
    ESTIMATE_MODEL_REASONING_EFFORT,
    ESTIMATE_MODEL_VERBOSITY,
    LLM_BASE_URL,
    OPENROUTER_API_KEY,
)
from prompts.loader import load_system_prompt, render_prompt

logger = logging.getLogger(__name__)

_DEFAULT_FATIGUE_PROFILE = {
    "axial": 0.3,
    "neural": 0.3,
    "peripheral": 0.5,
    "systemic": 0.3,
}

_SYSTEM_PROMPT = load_system_prompt("fatigue_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_fatigue_profile",
        "description": "Estimate 4-dimensional fatigue profile for an exercise",
        "parameters": {
            "type": "object",
            "properties": {
                "axial": {"type": "number", "description": "Spinal compression loading 0.0-1.0"},
                "neural": {"type": "number", "description": "CNS demand baseline 0.0-1.0"},
                "peripheral": {"type": "number", "description": "Local muscle damage potential 0.0-1.0"},
                "systemic": {"type": "number", "description": "Cardiovascular/metabolic demand 0.0-1.0"},
                "reasoning": {"type": "string", "description": "Brief explanation of the estimates"},
            },
            "required": ["axial", "neural", "peripheral", "systemic", "reasoning"],
        },
    },
}

def _round_to_nearest(value: float, step: float = 0.05) -> float:
    return round(round(value / step) * step, 2)

_BIG_LIFT_KEYS = {
    "squat": "squat",
    "back squat": "squat",
    "bench press": "bench",
    "bench": "bench",
    "deadlift": "deadlift",
    "conventional deadlift": "deadlift",
    "sumo deadlift": "deadlift",
}

def _match_lift_profile(
    exercise: dict,
    lift_profiles: list[dict] | None,
) -> dict | None:
    if not lift_profiles:
        return None
    name = (exercise.get("name") or "").strip().lower()
    category = (exercise.get("category") or "").strip().lower()
    target = _BIG_LIFT_KEYS.get(name) or (category if category in ("squat", "bench", "deadlift") else None)
    if not target:
        return None
    return next((p for p in lift_profiles if (p.get("lift") or "").lower() == target), None)

def _format_athlete_context(meta: dict | None) -> list[str]:
    if not meta:
        return []
    fields = [
        ("bodyweight_kg", meta.get("current_body_weight_kg")),
        ("height_cm", meta.get("height_cm")),
        ("arm_wingspan_cm", meta.get("arm_wingspan_cm")),
        ("leg_length_cm", meta.get("leg_length_cm")),
        ("sex", meta.get("sex")),
    ]
    present = [(k, v) for k, v in fields if v not in (None, "", 0)]
    if not present:
        return []
    lines = ["", "Athlete metrics:"]
    for k, v in present:
        lines.append(f"  {k}: {v}")
    return lines

def _format_lift_profile(profile: dict | None) -> list[str]:
    if not profile:
        return []
    lines = ["", f"Lift profile ({profile.get('lift', '?')}):"]
    for field in ("style_notes", "sticking_points", "primary_muscle", "volume_tolerance"):
        value = profile.get(field)
        if value:
            lines.append(f"  {field}: {value}")
    return lines if len(lines) > 1 else []

def _build_user_message(
    exercise: dict,
    program_meta: dict | None = None,
    lift_profiles: list[dict] | None = None,
) -> str:
    return render_prompt(
        "fatigue_user",
        exercise=exercise,
        athlete_metrics_lines=_format_athlete_context(program_meta),
        lift_profile_lines=_format_lift_profile(_match_lift_profile(exercise, lift_profiles)),
    )

async def estimate_fatigue_profile(
    exercise: dict,
    program_meta: dict | None = None,
    lift_profiles: list[dict] | None = None,
) -> dict:
    """Call LLM to estimate 4-dimensional fatigue profile for an exercise.

    When `program_meta` (body metrics) or `lift_profiles` are supplied and
    relevant to the exercise, they're included in the prompt as soft context
    to adjust for the athlete's leverages and stated style.
    """
    try:
        user_msg = _build_user_message(exercise, program_meta=program_meta, lift_profiles=lift_profiles)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": ESTIMATE_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "reasoning": {
                        "enabled": True,
                        "effort": ESTIMATE_MODEL_REASONING_EFFORT,
                    },
                    "verbosity": ESTIMATE_MODEL_VERBOSITY,
                    "tools": [_TOOL_SCHEMA],
                    "tool_choice": {"type": "function", "function": {"name": "estimate_fatigue_profile"}},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            logger.warning("[FatigueAI] No choices in response")
            return {**_DEFAULT_FATIGUE_PROFILE, "reasoning": "AI estimation failed: no response"}

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            logger.warning("[FatigueAI] No tool calls in response")
            return {**_DEFAULT_FATIGUE_PROFILE, "reasoning": "AI estimation failed: no tool call"}

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        args = json.loads(args_str)

        profile = {
            "axial": _round_to_nearest(float(args.get("axial", 0.3))),
            "neural": _round_to_nearest(float(args.get("neural", 0.3))),
            "peripheral": _round_to_nearest(float(args.get("peripheral", 0.5))),
            "systemic": _round_to_nearest(float(args.get("systemic", 0.3))),
            "reasoning": args.get("reasoning", ""),
        }
        return profile

    except Exception as e:
        logger.error(f"[FatigueAI] estimation failed: {e}")
        return {**_DEFAULT_FATIGUE_PROFILE, "reasoning": f"AI estimation failed: {e}"}
