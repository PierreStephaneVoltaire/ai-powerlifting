"""AI helpers for lift style profiles and INOL stimulus coefficients."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import (
    ESTIMATE_MODEL,
    ESTIMATE_MODEL_REASONING_EFFORT,
    ESTIMATE_MODEL_VERBOSITY,
    HEALTH_HELPER_MODEL,
    HEALTH_HELPER_MODEL_REASONING_EFFORT,
    HEALTH_HELPER_MODEL_VERBOSITY,
    LLM_BASE_URL,
    OPENROUTER_API_KEY,
)
from prompts.loader import load_system_prompt, render_prompt

logger = logging.getLogger(__name__)

LIFTS = {"squat", "bench", "deadlift"}
CONFIDENCE = {"low", "medium", "high"}
ESTIMATE_READY_THRESHOLD = 55

_REVIEW_SYSTEM_PROMPT = load_system_prompt("lift_profile_review_system")
_REWRITE_ESTIMATE_SYSTEM_PROMPT = load_system_prompt("lift_profile_rewrite_estimate_system")
_REWRITE_SYSTEM_PROMPT = load_system_prompt("lift_profile_rewrite_system")
_ESTIMATE_SYSTEM_PROMPT = load_system_prompt("lift_profile_estimate_system")

_REVIEW_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "review_lift_profile",
        "description": "Review lift profile quality and missing biomechanics details.",
        "parameters": {
            "type": "object",
            "properties": {
                "completeness_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "ready_for_coefficient": {"type": "boolean"},
                "missing_details": {"type": "array", "items": {"type": "string"}},
                "suggestions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["completeness_score", "ready_for_coefficient", "missing_details", "suggestions"],
        },
    },
}

_REWRITE_ESTIMATE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "rewrite_and_estimate_lift_profile",
        "description": "Rewrite lift profile text and estimate an INOL stimulus coefficient.",
        "parameters": {
            "type": "object",
            "properties": {
                "style_notes": {"type": "string"},
                "sticking_points": {"type": "string"},
                "primary_muscle": {"type": "string"},
                "stimulus_coefficient": {"type": "number", "minimum": 1, "maximum": 2},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "reasoning": {"type": "string"},
            },
            "required": [
                "style_notes",
                "sticking_points",
                "primary_muscle",
                "stimulus_coefficient",
                "confidence",
                "reasoning",
            ],
        },
    },
}

_REWRITE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "rewrite_lift_profile",
        "description": "Rewrite lift profile text fields without estimating stimulus coefficient.",
        "parameters": {
            "type": "object",
            "properties": {
                "style_notes": {"type": "string"},
                "sticking_points": {"type": "string"},
                "primary_muscle": {"type": "string"},
            },
            "required": ["style_notes", "sticking_points", "primary_muscle"],
        },
    },
}

_ESTIMATE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_lift_profile_stimulus",
        "description": "Estimate a 1-2 INOL stimulus coefficient from an existing lift profile.",
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


SCORE_EXPLANATION = (
    "Score is 0-100 completeness for estimating a lift-specific INOL stimulus coefficient: "
    "style/setup 40 points, sticking point 35 points, primary muscle driver 25 points."
)


def _profile_payload(profile: dict[str, Any]) -> str:
    keep = {
        "lift": profile.get("lift"),
        "style_notes": profile.get("style_notes", ""),
        "sticking_points": profile.get("sticking_points", ""),
        "primary_muscle": profile.get("primary_muscle", ""),
        "volume_tolerance": profile.get("volume_tolerance", "moderate"),
        "stimulus_coefficient": profile.get("stimulus_coefficient"),
    }
    return json.dumps(keep, indent=2)


def _round_to_nearest(value: float, step: float = 0.05) -> float:
    return round(round(value / step) * step, 2)


def _clamp_coeff(value: Any) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = 1.0
    return max(1.0, min(2.0, _round_to_nearest(raw)))


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _dedupe(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text or text.lower() in seen:
            continue
        out.append(text)
        seen.add(text.lower())
    return out


def _fallback_review(profile: dict[str, Any]) -> dict[str, Any]:
    lift = str(profile.get("lift", "")).lower()
    style = (profile.get("style_notes") or "").strip()
    sticking = (profile.get("sticking_points") or "").strip()
    primary = (profile.get("primary_muscle") or "").strip()
    style_l = style.lower()
    sticking_l = sticking.lower()
    primary_l = primary.lower()

    style_score = 0
    style_notes: list[str] = []
    if len(style) >= 40:
        style_score += 10
    else:
        style_notes.append("Add enough setup detail to identify your actual execution.")
    if _has_any(style_l, ("stance", "grip", "setup", "high bar", "low bar", "sumo", "conventional", "arch", "wedge")):
        style_score += 8
    else:
        style_notes.append("Mention stance/grip/setup.")
    if _has_any(style_l, ("rom", "range", "depth", "parallel", "touch", "lockout", "below", "above", "competition")):
        style_score += 8
    else:
        style_notes.append("Mention effective ROM versus competition standard.")
    if _has_any(style_l, ("torso", "bar path", "bracing", "elbow", "knee", "hip", "shoulder", "position")):
        style_score += 7
    else:
        style_notes.append("Mention the main position or bar path feature that changes difficulty.")
    if _has_any(style_l, ("eccentric", "tempo", "pause", "controlled", "advantage", "disadvantage", "leverage", "mechanical")):
        style_score += 7
    else:
        style_notes.append("Mention any tempo/eccentric or mechanical advantage/disadvantage.")

    sticking_score = 0
    sticking_notes: list[str] = []
    if len(sticking) >= 25:
        sticking_score += 10
    else:
        sticking_notes.append("Add more than a vague sticking point.")
    if _has_any(sticking_l, ("hole", "chest", "floor", "knee", "lockout", "mid", "below", "above", "off", "bottom", "top", "inch", "parallel")):
        sticking_score += 10
    else:
        sticking_notes.append("Name the exact ROM region where the lift slows or fails.")
    if _has_any(sticking_l, ("slow", "stall", "fail", "miss", "collapse", "shift", "lose", "weak", "break", "drift")):
        sticking_score += 8
    else:
        sticking_notes.append("Say what breaks down there: position, bracing, speed, or muscle output.")
    if _has_any(sticking_l, ("grind", "time", "pause", "tempo", "eccentric", "speed", "control", "stuck")):
        sticking_score += 7
    else:
        sticking_notes.append("Mention whether the weak point involves a grind, pause, or speed loss.")

    primary_score = 0
    primary_notes: list[str] = []
    if len(primary) >= 3:
        primary_score += 10
    else:
        primary_notes.append("Add the main muscle or position driving the lift.")
    if _has_any(primary_l, ("quad", "glute", "hamstring", "adductor", "pec", "chest", "tricep", "lat", "back", "erector", "hip", "shoulder")):
        primary_score += 10
    else:
        primary_notes.append("Name the actual muscle group or groups under meaningful tension.")
    if _has_any(primary_l, ("dominant", "driver", "drives", "tension", "weak", "limiting", "primary", "main")):
        primary_score += 5
    else:
        primary_notes.append("Say whether that muscle is the driver, limiter, or just a contributor.")

    breakdown = {
        "style_setup": {
            "score": style_score,
            "max": 40,
            "notes": style_notes,
        },
        "sticking_point": {
            "score": sticking_score,
            "max": 35,
            "notes": sticking_notes,
        },
        "primary_driver": {
            "score": primary_score,
            "max": 25,
            "notes": primary_notes,
        },
    }

    missing: list[str] = []
    if style_score < 30:
        missing.append("Style/setup needs stance or grip, effective ROM versus competition standard, and mechanical/tempo notes.")
    if sticking_score < 25:
        missing.append("Sticking point needs the exact ROM region and what breaks down there.")
    if primary_score < 18:
        missing.append("Primary driver needs the main muscle group and whether it is the driver or limiter.")

    score = style_score + sticking_score + primary_score
    return {
        "lift": lift or profile.get("lift"),
        "completeness_score": score,
        "ready_for_coefficient": score >= 75 and len(missing) == 0,
        "score_explanation": SCORE_EXPLANATION,
        "score_breakdown": breakdown,
        "missing_details": missing,
        "suggestions": _dedupe(style_notes + sticking_notes + primary_notes),
    }


def _fallback_rewrite_and_estimate(profile: dict[str, Any]) -> dict[str, Any]:
    review = _fallback_review(profile)
    return {
        "lift": profile.get("lift"),
        "style_notes": (profile.get("style_notes") or "").strip(),
        "sticking_points": (profile.get("sticking_points") or "").strip(),
        "primary_muscle": (profile.get("primary_muscle") or "").strip(),
        "volume_tolerance": profile.get("volume_tolerance", "moderate"),
        "stimulus_coefficient": 1.0,
        "stimulus_coefficient_confidence": "low",
        "stimulus_coefficient_reasoning": (
            "Defaulted to baseline because AI estimation was unavailable or the profile was too sparse."
        ),
        "stimulus_coefficient_updated_at": datetime.now(timezone.utc).isoformat(),
        "missing_details": review["missing_details"],
    }


def _fallback_rewrite(profile: dict[str, Any]) -> dict[str, Any]:
    review = _fallback_review(profile)
    return {
        "lift": profile.get("lift"),
        "style_notes": (profile.get("style_notes") or "").strip(),
        "sticking_points": (profile.get("sticking_points") or "").strip(),
        "primary_muscle": (profile.get("primary_muscle") or "").strip(),
        "volume_tolerance": profile.get("volume_tolerance", "moderate"),
        "missing_details": review["missing_details"],
    }


def _fallback_estimate(profile: dict[str, Any]) -> dict[str, Any]:
    review = _fallback_review(profile)
    return {
        "lift": profile.get("lift"),
        "stimulus_coefficient": 1.0,
        "stimulus_coefficient_confidence": "low",
        "stimulus_coefficient_reasoning": (
            "Defaulted to baseline because AI estimation was unavailable. "
            f"Profile score was {review['completeness_score']}%."
        ),
        "stimulus_coefficient_updated_at": datetime.now(timezone.utc).isoformat(),
        "ready_for_estimate": review["completeness_score"] >= ESTIMATE_READY_THRESHOLD,
        "estimate_ready_threshold": ESTIMATE_READY_THRESHOLD,
        "completeness_score": review["completeness_score"],
        "missing_details": review["missing_details"],
    }


async def _call_tool(
    system_prompt: str,
    user_msg: str,
    tool_schema: dict[str, Any],
    tool_name: str,
    *,
    model: str = ESTIMATE_MODEL,
    reasoning_effort: str = ESTIMATE_MODEL_REASONING_EFFORT,
    verbosity: str = ESTIMATE_MODEL_VERBOSITY,
) -> dict[str, Any] | None:
    if not OPENROUTER_API_KEY:
        return None

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "reasoning": {
                    "enabled": True,
                    "effort": reasoning_effort,
                },
                "verbosity": verbosity,
                "tools": [tool_schema],
                "tool_choice": {"type": "function", "function": {"name": tool_name}},
            },
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        return None
    tool_calls = choices[0].get("message", {}).get("tool_calls", [])
    if not tool_calls:
        return None
    args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
    return json.loads(args_str)


async def review_lift_profile(profile: dict[str, Any], *, use_helper_model: bool = False) -> dict[str, Any]:
    lift = str(profile.get("lift", "")).lower()
    if lift not in LIFTS:
        return {**_fallback_review(profile), "error": "Invalid lift. Expected squat, bench, or deadlift."}

    baseline = _fallback_review(profile)
    try:
        model_kwargs = {
            "model": HEALTH_HELPER_MODEL,
            "reasoning_effort": HEALTH_HELPER_MODEL_REASONING_EFFORT,
            "verbosity": HEALTH_HELPER_MODEL_VERBOSITY,
        } if use_helper_model else {}
        args = await _call_tool(
            _REVIEW_SYSTEM_PROMPT,
            render_prompt("lift_profile_user", action_verb="Review this lift profile", profile_payload=_profile_payload(profile)),
            _REVIEW_TOOL_SCHEMA,
            "review_lift_profile",
            **model_kwargs,
        )
        if not args:
            return baseline

        ai_missing = _dedupe(list(args.get("missing_details") or []))
        ai_suggestions = _dedupe(list(args.get("suggestions") or []))
        return {
            "lift": lift,
            "completeness_score": baseline["completeness_score"],
            "ready_for_coefficient": bool(baseline["ready_for_coefficient"]),
            "score_explanation": baseline["score_explanation"],
            "score_breakdown": baseline["score_breakdown"],
            "missing_details": ai_missing or baseline["missing_details"],
            "suggestions": ai_suggestions or baseline["suggestions"],
        }
    except Exception as e:
        logger.warning("[LiftProfileAI] review failed: %s", e)
        return baseline


async def rewrite_lift_profile(profile: dict[str, Any]) -> dict[str, Any]:
    lift = str(profile.get("lift", "")).lower()
    if lift not in LIFTS:
        result = _fallback_rewrite(profile)
        result["error"] = "Invalid lift. Expected squat, bench, or deadlift."
        return result

    try:
        args = await _call_tool(
            _REWRITE_SYSTEM_PROMPT,
            render_prompt("lift_profile_user", action_verb="Rewrite this lift profile without estimating a coefficient", profile_payload=_profile_payload(profile)),
            _REWRITE_TOOL_SCHEMA,
            "rewrite_lift_profile",
            model=HEALTH_HELPER_MODEL,
            reasoning_effort=HEALTH_HELPER_MODEL_REASONING_EFFORT,
            verbosity=HEALTH_HELPER_MODEL_VERBOSITY,
        )
        if not args:
            return _fallback_rewrite(profile)

        return {
            "lift": lift,
            "style_notes": str(args.get("style_notes", profile.get("style_notes", ""))).strip(),
            "sticking_points": str(args.get("sticking_points", profile.get("sticking_points", ""))).strip(),
            "primary_muscle": str(args.get("primary_muscle", profile.get("primary_muscle", ""))).strip(),
            "volume_tolerance": profile.get("volume_tolerance", "moderate"),
            "missing_details": (await review_lift_profile(profile, use_helper_model=True)).get("missing_details", []),
        }
    except Exception as e:
        logger.warning("[LiftProfileAI] rewrite failed: %s", e)
        return _fallback_rewrite(profile)


async def estimate_lift_profile_stimulus(profile: dict[str, Any]) -> dict[str, Any]:
    lift = str(profile.get("lift", "")).lower()
    if lift not in LIFTS:
        result = _fallback_estimate(profile)
        result["error"] = "Invalid lift. Expected squat, bench, or deadlift."
        return result

    review = _fallback_review(profile)
    if review["completeness_score"] < ESTIMATE_READY_THRESHOLD:
        result = _fallback_estimate(profile)
        result["error"] = (
            f"Profile score {review['completeness_score']}% is below the "
            f"{ESTIMATE_READY_THRESHOLD}% estimate threshold."
        )
        return result

    try:
        args = await _call_tool(
            _ESTIMATE_SYSTEM_PROMPT,
            render_prompt("lift_profile_user", action_verb="Estimate the stimulus coefficient for this lift profile", profile_payload=_profile_payload(profile)),
            _ESTIMATE_TOOL_SCHEMA,
            "estimate_lift_profile_stimulus",
        )
        if not args:
            return _fallback_estimate(profile)

        confidence = str(args.get("confidence", "low")).lower()
        if confidence not in CONFIDENCE:
            confidence = "low"

        return {
            "lift": lift,
            "stimulus_coefficient": _clamp_coeff(args.get("stimulus_coefficient", 1.0)),
            "stimulus_coefficient_confidence": confidence,
            "stimulus_coefficient_reasoning": str(args.get("reasoning", "")).strip(),
            "stimulus_coefficient_updated_at": datetime.now(timezone.utc).isoformat(),
            "ready_for_estimate": True,
            "estimate_ready_threshold": ESTIMATE_READY_THRESHOLD,
            "completeness_score": review["completeness_score"],
            "missing_details": (await review_lift_profile(profile)).get("missing_details", []),
        }
    except Exception as e:
        logger.warning("[LiftProfileAI] estimate failed: %s", e)
        return _fallback_estimate(profile)


async def rewrite_and_estimate_lift_profile(profile: dict[str, Any]) -> dict[str, Any]:
    lift = str(profile.get("lift", "")).lower()
    if lift not in LIFTS:
        result = _fallback_rewrite_and_estimate(profile)
        result["error"] = "Invalid lift. Expected squat, bench, or deadlift."
        return result

    try:
        args = await _call_tool(
            _REWRITE_ESTIMATE_SYSTEM_PROMPT,
            render_prompt("lift_profile_user", action_verb="Rewrite and estimate this lift profile", profile_payload=_profile_payload(profile)),
            _REWRITE_ESTIMATE_TOOL_SCHEMA,
            "rewrite_and_estimate_lift_profile",
            model=HEALTH_HELPER_MODEL,
            reasoning_effort=HEALTH_HELPER_MODEL_REASONING_EFFORT,
            verbosity=HEALTH_HELPER_MODEL_VERBOSITY,
        )
        if not args:
            return _fallback_rewrite_and_estimate(profile)

        confidence = str(args.get("confidence", "low")).lower()
        if confidence not in CONFIDENCE:
            confidence = "low"

        return {
            "lift": lift,
            "style_notes": str(args.get("style_notes", profile.get("style_notes", ""))).strip(),
            "sticking_points": str(args.get("sticking_points", profile.get("sticking_points", ""))).strip(),
            "primary_muscle": str(args.get("primary_muscle", profile.get("primary_muscle", ""))).strip(),
            "volume_tolerance": profile.get("volume_tolerance", "moderate"),
            "stimulus_coefficient": _clamp_coeff(args.get("stimulus_coefficient", 1.0)),
            "stimulus_coefficient_confidence": confidence,
            "stimulus_coefficient_reasoning": str(args.get("reasoning", "")).strip(),
            "stimulus_coefficient_updated_at": datetime.now(timezone.utc).isoformat(),
            "missing_details": (await review_lift_profile(profile, use_helper_model=True)).get("missing_details", []),
        }
    except Exception as e:
        logger.warning("[LiftProfileAI] rewrite/estimate failed: %s", e)
        return _fallback_rewrite_and_estimate(profile)
