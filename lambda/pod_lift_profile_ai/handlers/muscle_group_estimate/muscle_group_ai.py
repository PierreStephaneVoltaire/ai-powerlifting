"""LLM-based muscle group estimation for glossary exercises."""
from __future__ import annotations

import json
import logging

import httpx

from ai_config import (
    ESTIMATE_MODEL,
    ESTIMATE_MODEL_REASONING_EFFORT,
    ESTIMATE_MODEL_VERBOSITY,
    LLM_BASE_URL,
    OPENROUTER_API_KEY,
)
from prompts.loader import load_system_prompt, render_prompt

logger = logging.getLogger(__name__)

ALLOWED_MUSCLES = [
    "quads",
    "hamstrings",
    "glutes",
    "calves",
    "tibialis_anterior",
    "hip_flexors",
    "adductors",
    "chest",
    "triceps",
    "front_delts",
    "side_delts",
    "rear_delts",
    "lats",
    "traps",
    "rhomboids",
    "teres_major",
    "biceps",
    "forearms",
    "erectors",
    "lower_back",
    "core",
    "obliques",
    "serratus",
]

_DEFAULT_RESULT = {
    "primary_muscles": [],
    "secondary_muscles": [],
    "tertiary_muscles": [],
    "reasoning": "",
}

_SYSTEM_PROMPT = load_system_prompt("muscle_group_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_muscle_groups",
        "description": "Estimate primary, secondary, and tertiary muscle groups for an exercise",
        "parameters": {
            "type": "object",
            "properties": {
                "primary_muscles": {
                    "type": "array",
                    "items": {"type": "string", "enum": ALLOWED_MUSCLES},
                },
                "secondary_muscles": {
                    "type": "array",
                    "items": {"type": "string", "enum": ALLOWED_MUSCLES},
                },
                "tertiary_muscles": {
                    "type": "array",
                    "items": {"type": "string", "enum": ALLOWED_MUSCLES},
                },
                "reasoning": {"type": "string"},
            },
            "required": ["primary_muscles", "secondary_muscles", "tertiary_muscles", "reasoning"],
        },
    },
}

_ALIASES = {
    "tibialis anterior": "tibialis_anterior",
    "tibialis-anterior": "tibialis_anterior",
    "hip flexors": "hip_flexors",
    "hip-flexors": "hip_flexors",
    "front delts": "front_delts",
    "front deltoids": "front_delts",
    "side delts": "side_delts",
    "lateral delts": "side_delts",
    "rear delts": "rear_delts",
    "rear deltoids": "rear_delts",
    "teres major": "teres_major",
    "lower back": "lower_back",
    "adductor": "adductors",
    "adductors": "adductors",
    "serratus anterior": "serratus",
}

def _detect_related_lifts(exercise: dict) -> list[str]:
    name = (exercise.get("name") or "").strip().lower()
    category = (exercise.get("category") or "").strip().lower()
    related: list[str] = []

    if category == "squat" or "squat" in name:
        related.append("squat")
    if category == "bench" or "bench" in name:
        related.append("bench")
    if (
        category == "deadlift"
        or "deadlift" in name
        or "rdl" in name
        or "romanian" in name
        or "stiff leg" in name
        or "stiff-leg" in name
    ):
        related.append("deadlift")

    return related

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

def _select_lift_profiles(
    exercise: dict,
    lift_profiles: list[dict] | None,
) -> tuple[list[str], list[dict]]:
    if not lift_profiles:
        return [], []

    big_three = {
        (profile.get("lift") or "").strip().lower(): profile
        for profile in lift_profiles
        if (profile.get("lift") or "").strip().lower() in {"squat", "bench", "deadlift"}
    }
    if not big_three:
        return [], []

    related_lifts = _detect_related_lifts(exercise)
    ordered_lifts = related_lifts + [lift for lift in ("squat", "bench", "deadlift") if lift not in related_lifts]
    selected = [big_three[lift] for lift in ordered_lifts if lift in big_three]
    return related_lifts, selected

def _format_lift_profiles(related_lifts: list[str], profiles: list[dict]) -> list[str]:
    if not profiles:
        return []
    lines = ["", "Big-3 lift profiles (soft context; use only if the exercise is related):"]
    if related_lifts:
        lines.append(f"Most related competition lift(s): {', '.join(related_lifts)}")
    for profile in profiles:
        lines.append(f"")
        lines.append(f"Lift profile ({profile.get('lift', '?')}):")
        for field in ("style_notes", "sticking_points", "primary_muscle", "volume_tolerance"):
            value = profile.get(field)
            if value:
                lines.append(f"  {field}: {value}")
    return lines

def _build_user_message(
    exercise: dict,
    program_meta: dict | None = None,
    lift_profiles: list[dict] | None = None,
) -> str:
    related_lifts, contextual_profiles = _select_lift_profiles(exercise, lift_profiles)
    return render_prompt(
        "muscle_group_user",
        exercise=exercise,
        athlete_metrics_lines=_format_athlete_context(program_meta),
        lift_profile_lines=_format_lift_profiles(related_lifts, contextual_profiles),
    )

def _normalize_muscle(value: str) -> str | None:
    token = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not token:
        return None
    token = _ALIASES.get(token.replace("_", " "), token)
    return token if token in ALLOWED_MUSCLES else None

def _normalize_bucket(values: list[str] | None, seen: set[str], limit: int) -> list[str]:
    result: list[str] = []
    for raw in values or []:
        muscle = _normalize_muscle(raw)
        if not muscle or muscle in seen:
            continue
        result.append(muscle)
        seen.add(muscle)
        if len(result) >= limit:
            break
    return result

async def estimate_muscle_groups(
    exercise: dict,
    program_meta: dict | None = None,
    lift_profiles: list[dict] | None = None,
) -> dict:
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
                    "tool_choice": {"type": "function", "function": {"name": "estimate_muscle_groups"}},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            logger.warning("[MuscleGroupAI] No choices in response")
            return {**_DEFAULT_RESULT, "reasoning": "AI estimation failed: no response"}

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            logger.warning("[MuscleGroupAI] No tool calls in response")
            return {**_DEFAULT_RESULT, "reasoning": "AI estimation failed: no tool call"}

        args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
        args = json.loads(args_str)

        seen: set[str] = set()
        primary = _normalize_bucket(args.get("primary_muscles"), seen, limit=4)
        secondary = _normalize_bucket(args.get("secondary_muscles"), seen, limit=5)
        tertiary = _normalize_bucket(args.get("tertiary_muscles"), seen, limit=5)

        return {
            "primary_muscles": primary,
            "secondary_muscles": secondary,
            "tertiary_muscles": tertiary,
            "reasoning": args.get("reasoning", ""),
        }
    except Exception as exc:
        logger.error("[MuscleGroupAI] estimation failed: %s", exc)
        return {**_DEFAULT_RESULT, "reasoning": f"AI estimation failed: {exc}"}
