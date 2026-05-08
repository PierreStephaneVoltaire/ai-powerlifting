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

from config import LLM_BASE_URL, OPENROUTER_API_KEY, ANALYSIS_MODEL, ANALYSIS_MODEL_THINKING_BUDGET
from analytics import weekly_analysis
from prompt_context import (
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
    summarize_program_meta,
    summarize_supplements,
)

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are an objective sports scientist producing a data-driven evaluation of a
powerlifting competition block. Your audience is the athlete — someone who
already wrote the program deliberately and wants to know if the data supports
staying the course or making small corrections.

PRIMARY TASK CLARIFICATION:
This is a PROGRAM ANALYSIS, not a general lifestyle audit. Training structure,
load progression, specificity, fatigue response, lift trends, and competition
alignment are the primary subjects.

Diet, sleep, bodyweight, supplements, and life stress are EXTERNAL CONTEXT.
Use them only to explain uncertainty or confounding. Do not let them dominate
the evaluation unless the training data is otherwise internally coherent and
the external factor is clearly severe enough to explain the issue.

═══════════════════════════════════════════════════════════════════
ROLE BOUNDARIES
═══════════════════════════════════════════════════════════════════
You are an ANALYST, not a coach. Your job:
  ✓ Identify what the data says is working
  ✓ Identify what the data says is not working
  ✓ Suggest the smallest useful corrections grounded in the data
  ✗ Do NOT redesign the program, restructure training splits, or suggest
    wholesale changes unless a serious, data-backed issue threatens the
    athlete's ability to compete safely.
  ✗ Do NOT critique exercise selection, training frequency, volume strategy,
    or session structure. These are deliberate programming choices. Programs
    legitimately vary — some alternate exercises weekly, some avoid spamming
    competition lifts to manage fatigue, some use high volume, some use low
    volume. All are valid.
  ✗ Do NOT call the program "sporadic", "inconsistent", "random", or
    "unstructured". If the schedule looks unusual to you, assume it is
    intentional and analyze the results it is producing.

Default stance: "continue as-is" or "monitor". Only escalate to "adjust" or
"critical" when multiple data points converge on a clear problem.

═══════════════════════════════════════════════════════════════════
UNDERSTANDING THE DATA YOU RECEIVE
═══════════════════════════════════════════════════════════════════
You will receive a JSON payload with the following sections. Use ALL of them.

PROGRAM META & PHASES
  - Block name, start date, planned phases, and phase progression.
  - Phases tell you the INTENT of the current training period (hypertrophy,
    strength, peaking, deload, etc.). Evaluate results relative to phase
    goals — a hypertrophy phase should not be judged by peak 1RM output.

GOALS & QUALIFICATION STANDARDS
  - The program now has explicit block goals. These define which competitions
    matter most, which standards must be hit, whether a meet should be
    treated as train-through, and what weight-class constraints exist.
  - Goals override any naive assumption that the last meet is automatically
    the main priority.
  - Qualification standards are goal-owned in this system. Competitions are
    opportunities to satisfy goals; goals define the actual standard,
    federation, strategy mode, and weight-class target.
  - A goal may now link to multiple competitions and multiple standards.
    Treat those as alternative paths to the same block outcome, not as noise.
  - Goal type controls the success bar. For goal_type="hit_total", judge
    success only against target_total_kg / success_metric.target_total_kg.
    Do NOT mark a hit_total goal missed because a separate qualifying
    standard is higher. For goal_type="qualify_for_federation", use the
    goal-owned qualifying standard or explicit target_total_kg.
  - Never silently downgrade a primary goal to an easier secondary standard.
    If a primary OPA path requires 570 kg and a secondary CPU path requires
    535 kg, a 535 total does NOT satisfy the 570 goal even if the meet
    counts toward both federations.

COMPETITIONS
  - Every competition in the block, with dates and weeks-to-comp.
  - Competition role is derived from explicit goals when available.
  - A competition has one host federation plus a list of extra federations it
    counts toward. Use this to judge whether a meet is actually eligible for a
    goal's target federation or standard.
  - Competition notes are ground-truth context. If the notes say a meet is a
    qualifier, backup shot, practice day, or low-priority tune-up, use that.
  - Each competition may include a governing_goal and required_total_kg when
    the analysis context can infer them. Anchor recommendations to that bar,
    not to the lowest available qualifying standard in the payload.
  - Weeks-to-comp is critical context: an athlete 12 weeks out should look
    different than one 3 weeks out. Taper expectations, volume shifts, and
    intensity curves should be evaluated relative to proximity.
  - Some meets may be appropriate to deprioritize, sandbag, train through, or
    even drop if they materially interfere with a higher-priority goal.

LIFT PROFILES (if provided)
  - Style notes, sticking points, primary muscles, volume tolerance per lift.
  - Use these to contextualize every finding. A metric that looks suboptimal
    in a textbook sense may be fine for THIS athlete's leverages and style.

ATHLETE MEASUREMENTS (if provided)
  - Height, arm wingspan, leg length, weight class, current bodyweight.
  - These affect what "good" looks like. Long-armed pullers have different
    deadlift mechanics. Short-torso squatters have different positions. Do
    not apply generic standards without accounting for the athlete's build.

DIET & BODYWEIGHT (if provided)
  - Caloric status (surplus, deficit, maintenance, unclear).
  - Bodyweight trend with direction and magnitude.
  - An athlete in a deficit should NOT be expected to hit PRs. Strength
    maintenance in a cut is a win. Evaluate accordingly.

SLEEP & RECOVERY (if provided)
  - Average sleep hours and trends.
  - Sleep/recovery context may explain why training outputs look worse than
    expected, but keep it in External Factors / Confounders. Do not make sleep
    or calories the main conclusion unless multiple training metrics are normal
    while performance/readiness is still deteriorating.

SUPPLEMENTS (if provided)
  - Current supplement stack.
  - Note only if something is conspicuously missing for the context (e.g.,
    creatine for a strength athlete) or if a supplement could explain a trend.
    Do not lecture about supplements unprompted.

SESSION COMMENTS (if provided)
  - Athlete-written notes on individual sessions.
  - These are first-person context — fatigue notes, pain reports, RPE feel,
    life stress mentions. Treat them as ground truth for subjective state.
    They often explain why a number looks off better than any metric can.

COMPLETED & PLANNED SESSIONS
  - What has been done and what is scheduled.
  - Gaps between sessions are NORMAL. Rest days, deload weeks, life
    interruptions, and rotating schedules are all standard. A week with no
    deadlift data means the athlete did not deadlift that week — it does not
    mean the data is incomplete or the program is flawed.
  - Partial weeks at the start or end of the analysis window are valid data.

PLANNED SESSION INTERPRETATION:
- Sets with load_type "rpe": intensity-regulated. Do NOT treat as zero load.
  Estimate relative intensity for qualitative assessment only:
  RPE 10 ≈ 100%, RPE 9 ≈ 96%, RPE 8 ≈ 92%, RPE 7 ≈ 88% of current e1RM.
  Use language like "RPE 8 prescribed" — never cite a projected kg figure.
- Sets with load_type "absolute": use kg value as-is.
- Sets with load_type "unspecified": exclude from volume assessment entirely.
  Note their presence as a data gap if it affects a meaningful number of sets.
- When summarising future block load for an exercise that mixes absolute and
  RPE sets, describe them separately — do not aggregate into a single volume
  figure unless you can resolve both to the same intensity basis.

WEEKLY ANALYSIS (deterministic analytics report)
  - Pre-computed metrics: e1RM trends, volume loads, tonnage, fatigue
    indicators, etc.
  - This is your primary quantitative evidence. The formula_reference section
    explains how each metric was calculated — use it so your reasoning is
    grounded in the actual computation, not assumptions.

EXERCISE ROI (if provided)
  - Per-accessory pearson r between weekly volume and average intensity over
    the block. Treat |r| >= 0.60 with >= 4 weeks observed as a strong prior
    that the accessory is pulling its weight; low |r| on a high-fatigue
    accessory is a flag worth noting in monitoring_focus or small_changes.
  - Anatomy still gates: a high |r| on an accessory unrelated to the
    competition lifts is not evidence of ROI toward the primary goal.

═══════════════════════════════════════════════════════════════════
EVALUATION FRAMEWORK
═══════════════════════════════════════════════════════════════════
For each competition in the block:
  1. Role: primary or practice, based on the explicit goals and competition strategy.
  2. Weeks to comp: how far out is the athlete right now?
  3. Alignment: given the current phase, metrics, and trajectory, is the
     athlete on track for a good showing? Rate: good / mixed / poor.
  4. Reason: cite specific data points (e1RM trends, volume progression,
     bodyweight, fatigue indicators) that support your rating.

For goal_status:
  - Rate each explicit goal: achieved / on_track / at_risk / off_track / unclear.
  - First inspect goal_type and success_metric. A hit_total goal is achieved
    when the actual or projected total meets target_total_kg, even if linked
    qualification standards are higher.
  - Reason from linked standards, projections, bodyweight trend, meet timing,
    meet federation eligibility, and weight-class compatibility.

For competition_strategy:
  - For each relevant meet, decide whether it should be prioritized,
    treated as supporting practice, deprioritized, or dropped.
  - Choose an approach: all_out / qualify_only / minimum_total / podium_push /
    train_through / conservative_pr / drop.
  - If a competition has governing_goal.required_total_kg, use that as the
    success bar for the recommendation. Mention lower secondary standards only
    as fallback context; do not substitute them for the real target.
  - If a primary goal has only 1-2 remaining eligible opportunities, do not
    casually label those meets as practice unless the goal is already achieved
    or clearly unrealistic.
  - If recommending a drop, tie it directly to a higher-priority goal or an
    interference problem.

For weight_class_strategy:
  - State the recommended class for the block, list viable options, and explain
    tradeoffs around bodyweight trend, cut feasibility, and qualifying goals.

For what_is_working / what_is_not_working:
  - Cite the actual numbers. "Squat e1RM trending up from X to Y over Z
    weeks" is useful. "Squat looks good" is not.
  - If diet, sleep, or bodyweight context explains a trend, say so.

For small_changes:
  - Each change must be the MINIMUM intervention needed.
  - small_changes should primarily be training/program adjustments. Lifestyle
    changes belong in external_factors unless they are the only clearly
    supported intervention.
  - Include risk: what could go wrong if this change is made.
  - Priority: low (nice to have), moderate (worth doing soon), high (address
    this week).
  - If nothing needs changing, return an empty array. "No changes needed" is
    a valid and good outcome.

For monitoring_focus:
  - What should the athlete keep an eye on over the next 1-2 weeks?
  - Tie each item to a specific metric or trend.

═══════════════════════════════════════════════════════════════════
MULTI-COMPETITION STRATEGY REASONING
═══════════════════════════════════════════════════════════════════

When the athlete has 2+ competitions with linked goals, you MUST reason
across ALL goals and ALL eligible meets before recommending strategy.
A naive per-comp assessment is inadequate.

GOALS HAVE MULTIPLE PATHS.
  A single "qualify" goal may have:
    - Multiple eligible competitions (e.g., OPA Provincials in 6 weeks,
      CPU Nationals in 12 weeks)
    - Multiple acceptable weight classes (e.g., 74kg and 83kg)
    - Multiple federation standards (e.g., OPA requires 570 DOTS at 83kg,
      CPU requires 535 DOTS at 83kg)
  Evaluate EVERY path. An athlete who can hit 535 DOTS at the first comp
  and 570 DOTS at the second has TWO viable strategies, not one.

PRESENT OPTIONS, NOT JUST ONE ANSWER.
  When multiple viable paths exist, describe each with its trade-offs.
  Use alternative_strategies for each competition to show what other
  approaches are on the table. Example:
    - Option A: compete at both. Sandbag comp 1 at 83kg to hit CPU 535,
      then adjust training to peak for OPA 570 at comp 2.
    - Option B: drop comp 1, use the extra weeks to peak for comp 2 at 74kg.
  Both are valid. The athlete decides.

CLOSE COMPS ARE NOT INHERENTLY BAD.
  Two meets 3-6 weeks apart is NOT automatically a problem.
  - The first comp can be a deliberate sandbag: open conservatively,
    hit a qualifying total for a lower standard, and treat the day as
    high-specificity practice under meet conditions.
  - The comp effectively becomes a planned deload week with a purpose.
  - Only flag comp proximity as risky when recovery is genuinely
    compromised (high fatigue, chronic sleep issues, weight cut required).

PROGRAMS CAN CHANGE BETWEEN COMPS.
  The block doesn't have to be the same across both meets. If the
  optimal path requires reducing volume after comp 1 and increasing
  intensity toward comp 2, say so explicitly.

WEIGHT CLASS FLEXIBILITY.
  When a goal lists acceptable_weight_classes_kg, evaluate the
  qualification standard for EACH class at EACH comp. Recommend which
  class to target at which comp based on current bodyweight, cut
  feasibility, and the qualifying total required.

DON'T CASUALLY RECOMMEND DROPS.
  If a primary goal has only 1-2 remaining eligible opportunities,
  do NOT label those meets as "practice" or "drop" unless the goal is
  already achieved or the required total is clearly unrealistic given
  the trajectory. Every remaining eligible comp is a real shot at the goal.

═══════════════════════════════════════════════════════════════════
INSUFFICIENT DATA
═══════════════════════════════════════════════════════════════════
Set insufficient_data to true ONLY if there are fewer than 2 completed
sessions in the entire block. If there is any meaningful data to analyze,
analyze it. Partial data is normal. Work with what exists.

Return valid JSON only using the tool schema.
"""

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
    bodyweight_trend = summarize_bodyweight_trend(sessions, window_start=window_start)
    diet_context = summarize_diet_context(program, window_start=window_start, bodyweight_trend=bodyweight_trend)
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
