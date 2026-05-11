"""AI-powered exercise ROI / correlation analysis for powerlifting programs.

Analyzes whether accessory exercise volume trends correlate with improvements
in the main competition lifts (Squat, Bench, Deadlift).

Only produces anatomically plausible correlations — exercises working muscles
not involved in a given lift are excluded to avoid spurious correlations.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from prompts.loader import load_system_prompt, render_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("correlation_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_correlation_findings",
        "description": "Report accessory exercise to big lift correlation findings",
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "exercise": {"type": "string"},
                            "lift": {"type": "string", "enum": ["squat", "bench", "deadlift"]},
                            "correlation_direction": {"type": "string", "enum": ["positive", "negative", "unclear"]},
                            "strength": {"type": "string", "enum": ["strong", "moderate", "weak"]},
                            "reasoning": {"type": "string"},
                            "caveat": {"type": "string"},
                        },
                        "required": ["exercise", "lift", "correlation_direction", "strength", "reasoning", "caveat"],
                    },
                },
                "summary": {
                    "type": "string",
                    "description": "1-2 sentence overall summary of the correlation analysis",
                },
                "insufficient_data": {
                    "type": "boolean",
                    "description": "True if data is insufficient for meaningful analysis",
                },
                "insufficient_data_reason": {
                    "type": "string",
                    "description": "If insufficient_data is true, explain why",
                },
            },
            "required": ["findings", "summary"],
        },
    },
}


def _executed_sets(ex: dict) -> float:
    """Count completed or failed sets."""
    statuses = ex.get("set_statuses")
    if statuses and isinstance(statuses, list):
        return float(sum(1 for status in statuses if status in {"completed", "failed"}))
    return float(ex.get("sets") or 0)


def _build_weekly_e1rm(sessions: list[dict], cutoff_str: str) -> dict[int, dict[str, float]]:
    """Build weekly best e1RM estimates per big lift from sessions."""
    weekly: dict[int, dict[str, float]] = {}
    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        if s.get("date", "") < cutoff_str:
            continue
        if (s.get("block") or "current") != "current":
            continue
        wn = s.get("week_number", 0)
        if wn <= 0:
            continue

        for ex in s.get("exercises", []):
            name_lower = ex.get("name", "").lower()
            kg = ex.get("kg") or 0
            reps = ex.get("reps") or 0
            if kg <= 0 or reps <= 0 or _executed_sets(ex) <= 0:
                continue

            # Estimate e1RM via Epley formula
            e1rm = kg * (1 + reps / 30) if reps < 30 else kg

            # Map to big lift
            lift = None
            if "squat" in name_lower and "back" not in name_lower.replace("backout", ""):
                lift = "squat"
            elif name_lower in ("bench press", "bench") or (
                "bench" in name_lower and "press" in name_lower and "incline" not in name_lower
                and "close" not in name_lower and "pause" not in name_lower and "spoto" not in name_lower
            ):
                lift = "bench"
            elif "deadlift" in name_lower and "rdl" not in name_lower and "romanian" not in name_lower:
                lift = "deadlift"

            if lift:
                if wn not in weekly:
                    weekly[wn] = {}
                weekly[wn][lift] = max(weekly[wn].get(lift, 0), e1rm)

    return weekly


def _build_weekly_accessory_volume(sessions: list[dict], cutoff_str: str) -> dict[int, dict[str, float]]:
    """Build weekly volume (sets × reps × kg) per accessory exercise."""
    weekly: dict[int, dict[str, float]] = {}
    big_lift_names = frozenset(["squat", "bench", "bench press", "deadlift"])

    for s in sessions:
        if not (s.get("completed") or s.get("status") in ("logged", "completed")):
            continue
        if s.get("date", "") < cutoff_str:
            continue
        if (s.get("block") or "current") != "current":
            continue
        wn = s.get("week_number", 0)
        if wn <= 0:
            continue

        for ex in s.get("exercises", []):
            name = ex.get("name", "")
            name_lower = name.lower().strip()

            # Skip main competition lifts (keep accessories)
            if name_lower in big_lift_names:
                continue
            if name_lower in ("squat", "bench press", "deadlift"):
                continue

            vol = _executed_sets(ex) * (ex.get("reps") or 0) * (ex.get("kg") or 0)
            if vol <= 0:
                continue

            if wn not in weekly:
                weekly[wn] = {}
            weekly[wn][name] = weekly[wn].get(name, 0) + vol

    return weekly


def _build_user_message(
    weeks: int,
    window_start: str,
    weekly_e1rm: dict,
    weekly_accessory: dict,
    lift_profiles: list[dict],
    athlete_measurements: dict | None = None,
    caloric_status: str | None = None,
    bodyweight_trend: dict | None = None,
    weeks_to_primary_comp: float | None = None,
    exercise_roi: list[dict] | None = None,
) -> str:
    all_weeks = sorted(set(list(weekly_e1rm.keys()) + list(weekly_accessory.keys())))
    if not all_weeks:
        return f"## Analysis window: Last {weeks} weeks (from {window_start})\n\nNo data available.\n"

    acc_totals: dict[str, float] = {}
    for wn, exes in weekly_accessory.items():
        for name, vol in exes.items():
            acc_totals[name] = acc_totals.get(name, 0) + vol
    top_accessories = sorted(acc_totals.items(), key=lambda x: -x[1])[:20]

    return render_prompt(
        "correlation_user",
        weeks=weeks,
        window_start=window_start,
        weeks_to_primary_comp=weeks_to_primary_comp,
        lift_profiles=lift_profiles or [],
        athlete_measurements=athlete_measurements or {},
        caloric_status=caloric_status,
        bodyweight_trend=bodyweight_trend,
        all_weeks=all_weeks,
        weekly_e1rm=weekly_e1rm,
        weekly_accessory=weekly_accessory,
        top_accessories=top_accessories,
        exercise_roi=exercise_roi,
    )


async def generate_correlation_report(
    sessions: list[dict],
    lift_profiles: list[dict],
    weeks: int,
    window_start: str,
    program: dict | None = None,
) -> dict[str, Any]:
    """Call LLM to generate correlation findings for the given session window."""
    weekly_e1rm = _build_weekly_e1rm(sessions, window_start)
    weekly_accessory = _build_weekly_accessory_volume(sessions, window_start)

    distinct_weeks = len(set(list(weekly_e1rm.keys()) + list(weekly_accessory.keys())))
    if distinct_weeks < 4:
        return {
            "findings": [],
            "summary": "Insufficient data for correlation analysis.",
            "insufficient_data": True,
            "insufficient_data_reason": f"Only {distinct_weeks} weeks of data found. Need at least 4.",
        }

    # Build enriched context
    meta = program.get("meta", {}) if program else {}
    athlete_measurements = {
        "height_cm": meta.get("height_cm"),
        "arm_wingspan_cm": meta.get("arm_wingspan_cm"),
        "leg_length_cm": meta.get("leg_length_cm"),
        "weight_class_kg": meta.get("weight_class_kg"),
        "current_body_weight_kg": meta.get("current_body_weight_kg"),
    }

    # Weeks to primary comp
    exercise_roi: list[dict] | None = None
    try:
        from prompt_context import (
            summarize_competitions,
            summarize_bodyweight_trend,
            summarize_diet_context,
            summarize_exercise_roi,
        )
        comp_summary = summarize_competitions(program)
        primary = comp_summary.get("primary_competition") or {}
        weeks_to_primary_comp = primary.get("weeks_to_comp")

        bw_trend = summarize_bodyweight_trend(program.get("sessions", []), weight_log=program.get("weight_log", []))
        caloric_context = summarize_diet_context(program, bodyweight_trend=bw_trend)
        caloric_status = caloric_context.get("status", "unclear")
        bodyweight_trend = bw_trend

        exercise_roi = summarize_exercise_roi(program, sessions=sessions, top_n=10) or None
    except Exception:
        weeks_to_primary_comp = None
        caloric_status = None
        bodyweight_trend = None

    user_msg = _build_user_message(
        weeks, window_start, weekly_e1rm, weekly_accessory, lift_profiles,
        athlete_measurements=athlete_measurements,
        caloric_status=caloric_status,
        bodyweight_trend=bodyweight_trend,
        weeks_to_primary_comp=weeks_to_primary_comp,
        exercise_roi=exercise_roi,
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
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

        return {
            "findings": args.get("findings", []),
            "summary": args.get("summary", ""),
            "insufficient_data": args.get("insufficient_data", False),
            "insufficient_data_reason": args.get("insufficient_data_reason", ""),
        }

    except Exception as e:
        logger.error(f"[CorrelationAI] generation failed: {e}")
        return {
            "findings": [],
            "summary": f"AI analysis failed: {e}",
            "insufficient_data": True,
            "insufficient_data_reason": str(e),
        }
