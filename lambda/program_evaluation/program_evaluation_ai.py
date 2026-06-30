"""LLM-powered full-block program evaluation for powerlifting programs.

This uses the full completed/current block context plus planned sessions,
competition targets, athlete measurements, lift profiles, nutrition trends,
and the deterministic analytics report to produce a conservative program
assessment.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

import httpx

from ai_config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from .analytics import weekly_analysis
from prompts.loader import load_system_prompt
from .prompt_context import (
    FORMULA_REFERENCE,
    summarize_bodyweight_trend,
    summarize_completed_sessions,
    summarize_competitions,
    summarize_diet_context,
    summarize_exercise_roi,
    summarize_goals,
    summarize_lift_profiles,
    summarize_meet_interference,
    summarize_measurements,
    summarize_phases,
    summarize_planned_sessions,
    summarize_program_notes,
    summarize_program_meta,
    summarize_supplements,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_system_prompt("program_evaluation_system")

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_program_evaluation",
        "description": "Report a conservative performance evaluation for a powerlifting block",
        "parameters": {
            "type": "object",
            "properties": {
                "stance": {
                    "type": "string",
                    "enum": ["continue", "monitor", "adjust", "critical"],
                    "description": "Overall recommendation stance",
                },
                "summary": {
                    "type": "string",
                    "description": "2-4 sentence overall summary of the block",
                },
                "what_is_working": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "what_is_not_working": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "competition_alignment": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "competition": {"type": "string"},
                            "role": {"type": "string", "enum": ["primary", "practice"]},
                            "weeks_to_comp": {"type": ["number", "null"]},
                            "alignment": {"type": "string", "enum": ["good", "mixed", "poor"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["competition", "role", "alignment", "reason"],
                    },
                },
                "goal_status": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string"},
                            "priority": {"type": "string", "enum": ["primary", "secondary", "optional"]},
                            "status": {"type": "string", "enum": ["achieved", "on_track", "at_risk", "off_track", "unclear"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["goal", "priority", "status", "reason"],
                    },
                },
                "competition_strategy": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "competition": {"type": "string"},
                            "priority": {"type": "string", "enum": ["prioritize", "supporting", "practice", "deprioritize", "drop"]},
                            "approach": {"type": "string", "enum": ["all_out", "qualify_only", "minimum_total", "podium_push", "train_through", "conservative_pr", "drop"]},
                            "reason": {"type": "string"},
                            "alternative_strategies": {
                                "type": "array",
                                "description": "Alternative viable approaches for this competition. Present when multiple paths to the athlete's goals exist.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "approach": {"type": "string", "enum": ["all_out", "qualify_only", "minimum_total", "podium_push", "train_through", "conservative_pr", "drop"]},
                                        "target_total_kg": {"type": ["number", "null"]},
                                        "target_weight_class_kg": {"type": ["number", "null"]},
                                        "reason": {"type": "string"},
                                    },
                                    "required": ["approach", "reason"],
                                },
                            },
                        },
                        "required": ["competition", "priority", "approach", "reason"],
                    },
                },
                "weight_class_strategy": {
                    "type": "object",
                    "properties": {
                        "recommendation": {"type": "string"},
                        "recommended_weight_class_kg": {"type": ["number", "null"]},
                        "viable_options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "weight_class_kg": {"type": "number"},
                                    "suitability": {"type": "string", "enum": ["best", "viable", "risky"]},
                                    "reason": {"type": "string"},
                                },
                                "required": ["weight_class_kg", "suitability", "reason"],
                            },
                        },
                    },
                    "required": ["recommendation", "recommended_weight_class_kg", "viable_options"],
                },
                "small_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "change": {"type": "string"},
                            "why": {"type": "string"},
                            "risk": {"type": "string"},
                            "priority": {"type": "string", "enum": ["low", "moderate", "high"]},
                        },
                        "required": ["change", "why", "risk", "priority"],
                    },
                },
                "external_factors": {
                    "type": "array",
                    "description": "Diet, sleep, bodyweight, supplements, stress, or other external confounders separated from program structure.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "factor": {"type": "string"},
                            "impact": {"type": "string", "enum": ["low", "moderate", "high"]},
                            "reason": {"type": "string"},
                            "separate_from_program": {"type": "boolean"},
                        },
                        "required": ["factor", "impact", "reason", "separate_from_program"],
                    },
                },
                "monitoring_focus": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "conclusion": {
                    "type": "string",
                    "description": "Short final recommendation",
                },
                "insufficient_data": {
                    "type": "boolean",
                },
                "insufficient_data_reason": {
                    "type": "string",
                },
            },
            "required": ["stance", "summary", "what_is_working", "what_is_not_working", "competition_alignment", "goal_status", "competition_strategy", "weight_class_strategy", "small_changes", "external_factors", "monitoring_focus", "conclusion"],
        },
    },
}

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None

def _current_block_sessions(program: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in program.get("sessions", []) if (s.get("block") or "current") == "current"]

def _analysis_weeks(program: dict[str, Any], sessions: list[dict[str, Any]]) -> int:
    meta = program.get("meta", {})
    program_start = _parse_date(meta.get("program_start"))
    if program_start:
        return max(1, ((date.today() - program_start).days // 7) + 1)

    weeks = [int(s.get("week_number") or 0) for s in sessions if s.get("week_number")]
    return max(1, max(weeks) if weeks else 1)

def _sanitize_floats(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None so json.dumps produces valid JSON."""
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

def _build_user_message(program: dict[str, Any], federation_library: dict[str, Any] | None = None) -> str:
    meta = program.get("meta", {})
    sessions = _current_block_sessions(program)
    current_weeks = _analysis_weeks(program, sessions)
    window_start = _parse_date(meta.get("program_start"))

    completed_weeks = sorted({int(s.get("week_number") or 0) for s in sessions if (s.get("completed") or s.get("status") in ("logged", "completed")) and s.get("week_number")})
    bodyweight_trend = summarize_bodyweight_trend(
        sessions,
        weight_log=program.get("weight_log", []),
        window_start=window_start,
    )
    diet_context = summarize_diet_context(program, window_start=window_start, bodyweight_trend=bodyweight_trend)
    program_notes = summarize_program_notes(program, window_start=window_start)
    goals = summarize_goals(program, federation_library=federation_library)
    competitions = summarize_competitions(
        program,
        federation_library=federation_library,
        competition_goal_priorities=goals.get("competition_goal_priorities"),
    )
    meet_interference = summarize_meet_interference(
        program,
        competition_goal_priorities=goals.get("competition_goal_priorities"),
    )
    lift_profiles = summarize_lift_profiles(program.get("lift_profiles"))
    phases = summarize_phases(program.get("phases"))
    measurements = summarize_measurements(meta)
    supplements = summarize_supplements(program)
    completed_sessions = summarize_completed_sessions(sessions)
    planned_sessions = summarize_planned_sessions(sessions)
    weekly_report = weekly_analysis(program, sessions, weeks=current_weeks, block="current")
    exercise_roi = summarize_exercise_roi(program, sessions=sessions, top_n=15)
    current_block_completed_sessions = len([s for s in sessions if s.get("completed") or s.get("status") in ("logged", "completed")])

    payload = {
        "task": "Evaluate the current powerlifting block and judge how well it is directing the athlete toward the competition goals.",
        "instructions": {
            "tone": "objective sports scientist",
            "stance_preference": "conservative",
            "do_not": [
                "recommend wholesale redesigns unless a serious issue exists",
                "overreact to a single metric without context",
            ],
            "focus": [
                "overall trajectory",
                "what is going right",
                "what is going wrong",
                "goal alignment for each competition",
                "federation eligibility and weight-class fit for each linked goal",
                "small useful adjustments only",
                "whether to continue as-is, monitor, or make limited changes",
            ],
        },
        "program_meta": summarize_program_meta(meta),
        "phases": phases,
        "goals": goals,
        "full_block_summary": {
            "analysis_weeks": current_weeks,
            "completed_sessions": current_block_completed_sessions,
            "completed_weeks": completed_weeks,
        },
        "completed_block_weeks": completed_weeks,
        "competitions": competitions,
        "meet_interference": meet_interference,
        "lift_profiles": lift_profiles,
        "athlete_measurements": measurements,
        "supplements": supplements,
        "diet_context": diet_context,
        "dated_program_notes": program_notes,
        "bodyweight_trend": bodyweight_trend,
        "completed_sessions": completed_sessions,
        "planned_sessions": planned_sessions,
        "weekly_analysis": weekly_report,
        "exercise_roi": exercise_roi,
        "formula_reference": FORMULA_REFERENCE,
    }

    return json.dumps(_sanitize_floats(payload), indent=2, default=str)

async def generate_program_evaluation_report(
    program: dict[str, Any],
    federation_library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the LLM to generate a conservative block evaluation report."""
    user_msg = _build_user_message(program, federation_library=federation_library)
    logger.info(f"[ProgramEvaluationAI] model={ANALYSIS_MODEL} payload_chars={len(user_msg)}")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
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
                logger.error(f"[ProgramEvaluationAI] HTTP {resp.status_code} from OpenRouter: {resp.text[:2000]}")
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
            "stance": args.get("stance", "monitor"),
            "summary": args.get("summary", ""),
            "what_is_working": args.get("what_is_working", []),
            "what_is_not_working": args.get("what_is_not_working", []),
            "competition_alignment": args.get("competition_alignment", []),
            "goal_status": args.get("goal_status", []),
            "competition_strategy": args.get("competition_strategy", []),
            "weight_class_strategy": args.get("weight_class_strategy", {"recommendation": "", "recommended_weight_class_kg": None, "viable_options": []}),
            "small_changes": args.get("small_changes", []),
            "external_factors": args.get("external_factors", []),
            "monitoring_focus": args.get("monitoring_focus", []),
            "conclusion": args.get("conclusion", ""),
            "insufficient_data": args.get("insufficient_data", False),
            "insufficient_data_reason": args.get("insufficient_data_reason", ""),
        }

    except Exception as e:
        logger.error(f"[ProgramEvaluationAI] generation failed: {e}")
        return {
            "stance": "monitor",
            "summary": f"AI evaluation failed: {e}",
            "what_is_working": [],
            "what_is_not_working": [],
            "competition_alignment": [],
            "goal_status": [],
            "competition_strategy": [],
            "weight_class_strategy": {"recommendation": "", "recommended_weight_class_kg": None, "viable_options": []},
            "small_changes": [],
            "external_factors": [],
            "monitoring_focus": [],
            "conclusion": "Continue monitoring until the AI report can be regenerated.",
            "insufficient_data": True,
            "insufficient_data_reason": str(e),
        }
