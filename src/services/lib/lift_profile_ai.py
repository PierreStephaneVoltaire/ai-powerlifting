import json
import logging
from typing import Any

from services.ai import completion
from services.lib.ai_config import ESTIMATE_MODEL, ESTIMATE_MODEL_REASONING_EFFORT, ESTIMATE_MODEL_VERBOSITY
from services.lib.lift_profiles import LIFTS, clean, clean_options, describe, fields, missing, now, suggest_tool_schema
from services.lib.prompts.loader import load_system_prompt

logger = logging.getLogger(__name__)
CONFIDENCE = {"low", "medium", "high"}

_SUGGEST_SYSTEM_PROMPT = load_system_prompt("lift_profile_suggest_system")
_ESTIMATE_SYSTEM_PROMPT = load_system_prompt("lift_profile_estimate_system")
_ESTIMATE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_lift_profile_stimulus",
        "description": "Estimate a 1-2 INOL stimulus coefficient from a structured lift profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "stimulus_coefficient": {"type": "number", "minimum": 1, "maximum": 2},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "reasoning": {"type": "string"},
            },
            "required": ["stimulus_coefficient", "confidence", "reasoning"],
        },
    },
}


async def _call_tool(system_prompt: str, user_msg: str, tool_schema: dict, tool_name: str) -> dict | None:
    resp = await completion({
        "model": ESTIMATE_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
        "reasoning": {"enabled": True, "effort": ESTIMATE_MODEL_REASONING_EFFORT},
        "verbosity": ESTIMATE_MODEL_VERBOSITY,
        "tools": [tool_schema],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
    })
    resp.raise_for_status()
    choices = resp.json().get("choices", [])
    tool_calls = choices[0].get("message", {}).get("tool_calls", []) if choices else []
    return json.loads(tool_calls[0].get("function", {}).get("arguments", "{}")) if tool_calls else None


async def suggest_options(lift: str, description: str, profile: dict | None = None) -> dict:
    if lift not in LIFTS:
        raise ValueError("Invalid lift. Expected squat, bench, or deadlift.")
    current = clean({**(profile or {}), "lift": lift}) or {"options": {}}
    available = {field["key"]: {"label": field["label"], "options": {option["value"]: option["label"] for option in field["options"]}} for field in fields(lift)}
    user_msg = json.dumps({"lift": lift, "fields": available, "already_selected": current["options"], "description": str(description or "").strip()}, indent=2)
    args = await _call_tool(_SUGGEST_SYSTEM_PROMPT, user_msg, suggest_tool_schema(lift), "select_lift_profile_options") or {}
    suggested = clean_options(lift, {**current["options"], **{key: value for key, value in args.items() if value}})
    tolerance = args.get("volume_tolerance") if args.get("volume_tolerance") in ("low", "moderate", "high") else None
    return {"lift": lift, "options": suggested, "volume_tolerance": tolerance, "changed": sorted(key for key in suggested if suggested.get(key) != current["options"].get(key))}


def _clamp(value: Any) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = 1.0
    return max(1.0, min(2.0, round(round(raw / 0.05) * 0.05, 2)))


async def estimate_stimulus(profile: dict) -> dict:
    profile = clean(profile)
    if profile is None:
        raise ValueError("Invalid lift. Expected squat, bench, or deadlift.")
    gaps = missing(profile)
    if gaps:
        raise ValueError("Choose every option before estimating: " + ", ".join(gaps))
    args = await _call_tool(_ESTIMATE_SYSTEM_PROMPT, "Estimate the stimulus coefficient for this lift profile:\n" + json.dumps(describe(profile), indent=2), _ESTIMATE_TOOL_SCHEMA, "estimate_lift_profile_stimulus")
    if not args:
        raise ValueError("The estimate returned no result")
    confidence = str(args.get("confidence", "low")).lower()
    return {
        "lift": profile["lift"],
        "stimulus_coefficient": _clamp(args.get("stimulus_coefficient")),
        "stimulus_coefficient_confidence": confidence if confidence in CONFIDENCE else "low",
        "stimulus_coefficient_reasoning": str(args.get("reasoning", "")).strip(),
        "stimulus_coefficient_updated_at": now(),
    }
