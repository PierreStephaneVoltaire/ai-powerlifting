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

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a biomechanics-focused data analyst reviewing powerlifting training logs.
Your ONLY job is to identify anatomically plausible correlations between accessory
exercise volume trends and changes in Squat, Bench Press, and Deadlift e1RM estimates.

UNDERSTANDING THE DATA:
1. The data is aggregated into WEEK buckets. A dash ("-") for a lift or accessory in a
   given week means that exercise was NOT PERFORMED that week. This is NORMAL.
   Real powerlifting programs intentionally rotate, periodize, and alternate exercises.
   Deadlifting once a week, twice a week, every other week, or taking planned deload/rest
   weeks are ALL standard approaches. Do NOT treat gaps, dashes, or low frequency as a
   data quality problem.
2. The analysis window may start or end mid-week. A partial week at the boundary is still
   valid data — do not discard it or penalize the analysis for it.
3. If a competition lift only appears in 2-3 of the weeks, you can still analyze trends
   for that lift using the weeks where data exists. You need at least 2 data points for a
   given lift to comment on its trend. If only 1 data point exists for a lift, skip that
   lift — do not flag the entire analysis as insufficient.
4. You are seeing a WINDOW into a larger program. Do not make assumptions about what
   happened before or after this window. Work strictly with what is provided.

WHAT YOU MUST NOT DO:
- Do NOT comment on, critique, or editorialize about the athlete's programming choices,
  training frequency, exercise selection, volume levels, or program structure.
- Do NOT call the program "sporadic", "inconsistent", "random", or any similar judgment.
- Do NOT speculate about whether the athlete "should" be training differently.
- Do NOT flag insufficient data unless there are literally fewer than 2 weeks with ANY
  recorded activity. If there is data to analyze, analyze it.
- Do NOT analyze competition lifts against each other (e.g., squat vs deadlift). Only
  analyze accessory → competition lift relationships.

ANATOMICAL PLAUSIBILITY FILTER:
Only report correlations where the accessory exercise works muscles that are PRIMARY or
SIGNIFICANT SECONDARY movers in the competition lift. Examples:
  - Tricep work → Bench Press ✓ (triceps are primary movers)
  - Leg Press → Squat ✓ (quad overlap)
  - Lat Pulldown → Deadlift ✓ (lats stabilize the pull)
  - Bicep Curls → Bench Press ✗ (biceps are not primary bench movers)
  - Calf Raises → Squat ✗ (negligible role in squat mechanics)
High correlation between anatomically UNRELATED exercises and a lift is a false positive.
Do not report it.

LIFT PROFILE CONTEXT:
Use the athlete's stated lift profiles (style, muscle dominance, sticking points) to
weight relevance. A tricep-dominant bencher benefits more from tricep accessories. A
quad-dominant squatter benefits more from quad accessories. Sticking point at lockout
means lockout-targeting exercises matter more. Apply this lens when rating strength.

EXERCISE ROI PRIOR (when provided):
The payload may include an "Accessory Exercise ROI" table with Pearson r values between
weekly volume and average intensity for each accessory. Treat these as a QUANTITATIVE
PRIOR on top of anatomical reasoning:
  - |r| >= 0.60 with >= 4 weeks observed → strong statistical signal; upgrade the
    "strength" rating of an anatomically-plausible finding by one level.
  - 0.30 <= |r| < 0.60 → moderate prior; use as supporting evidence only.
  - |r| < 0.30 or fewer than 3 weeks → weak/noisy; fall back to anatomical reasoning.
  - A high |r| on an anatomically unrelated accessory is STILL a false positive. The
    anatomical filter is the gate; ROI only tunes the strength rating for relationships
    that already pass the filter.
Do NOT invent correlations from the ROI table alone.

FOR EACH FINDING, PROVIDE:
  - exercise: accessory exercise name
  - lift: "squat", "bench", or "deadlift"
  - correlation_direction: "positive", "negative", or "unclear"
  - strength: "strong", "moderate", or "weak"
  - reasoning: 2-3 sentences on WHY this makes biomechanical sense given the data trend
  - caveat: note that correlation ≠ causation and any confounds

Be conservative. Fewer high-confidence findings are better than many speculative ones.
Output ONLY valid JSON in the format specified by the tool call.
"""

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
            if kg <= 0 or reps <= 0:
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

            vol = (ex.get("sets") or 0) * (ex.get("reps") or 0) * (ex.get("kg") or 0)
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
    lines = [f"## Analysis window: Last {weeks} weeks (from {window_start})\n"]

    if weeks_to_primary_comp is not None:
        lines.append(f"**Weeks to primary competition:** {weeks_to_primary_comp:.1f}\n")

    # Lift profiles
    if lift_profiles:
        lines.append("## Athlete Lift Profiles\n")
        for p in lift_profiles:
            lift = p.get("lift", "?")
            lines.append(f"### {lift.title()}")
            if p.get("style_notes"):
                lines.append(f"  Style: {p['style_notes']}")
            if p.get("sticking_points"):
                lines.append(f"  Sticking points: {p['sticking_points']}")
            if p.get("primary_muscle"):
                lines.append(f"  Primary muscle: {p['primary_muscle']}")
            if p.get("volume_tolerance"):
                lines.append(f"  Volume tolerance: {p['volume_tolerance']}")
        lines.append("")

    # Athlete measurements
    if athlete_measurements and any(v for v in athlete_measurements.values()):
        lines.append("## Athlete Measurements\n")
        for k, v in athlete_measurements.items():
            if v is not None:
                lines.append(f"  {k.replace('_', ' ')}: {v}")
        lines.append("")

    # Caloric / body weight context
    if caloric_status:
        lines.append(f"**Caloric status:** {caloric_status}\n")
    if bodyweight_trend:
        direction = bodyweight_trend.get("direction", "unclear")
        change = bodyweight_trend.get("change")
        latest = bodyweight_trend.get("latest")
        if latest is not None:
            change_str = f" ({'+' if change and change > 0 else ''}{change} kg over window)" if change is not None else ""
            lines.append(f"**Body weight trend:** {latest} kg, {direction}{change_str}\n")

    # Weekly e1RM table
    all_weeks = sorted(set(list(weekly_e1rm.keys()) + list(weekly_accessory.keys())))
    if not all_weeks:
        lines.append("No data available.\n")
        return "\n".join(lines)

    lines.append("## Weekly e1RM Estimates (kg)\n")
    lines.append("| Week | Squat | Bench | Deadlift |")
    lines.append("|------|-------|-------|----------|")
    for wn in all_weeks:
        e = weekly_e1rm.get(wn, {})
        squat = f"{e.get('squat', 0):.1f}" if e.get("squat") else "-"
        bench = f"{e.get('bench', 0):.1f}" if e.get("bench") else "-"
        dead = f"{e.get('deadlift', 0):.1f}" if e.get("deadlift") else "-"
        lines.append(f"| W{wn} | {squat} | {bench} | {dead} |")
    lines.append("")

    # Top accessories by total volume
    acc_totals: dict[str, float] = {}
    for wn, exes in weekly_accessory.items():
        for name, vol in exes.items():
            acc_totals[name] = acc_totals.get(name, 0) + vol

    top_accessories = sorted(acc_totals.items(), key=lambda x: -x[1])[:20]

    if top_accessories:
        lines.append("## Weekly Accessory Volume (sets × reps × kg) — Top 20\n")
        header = "| Week | " + " | ".join(name for name, _ in top_accessories) + " |"
        sep = "|------|" + "|".join("---" for _ in top_accessories) + "|"
        lines.append(header)
        lines.append(sep)
        for wn in all_weeks:
            row = f"| W{wn} | "
            for name, _ in top_accessories:
                vol = weekly_accessory.get(wn, {}).get(name, 0)
                row += (f"{vol:.0f}" if vol else "-") + " | "
            lines.append(row)
        lines.append("")

    if exercise_roi:
        lines.append("## Accessory Exercise ROI (pearson r between weekly volume and avg intensity)\n")
        lines.append("| Exercise | Pearson r | Weeks |")
        lines.append("|----------|-----------|-------|")
        for row in exercise_roi:
            lines.append(
                f"| {row.get('exercise', '?')} | {row.get('pearson_r', 0):+.3f} | "
                f"{row.get('weeks_observed', 0)} |"
            )
        lines.append("")

    lines.append(
        "## Task\nAnalyze the data above. Identify which accessory exercises have volume trends "
        "that plausibly correlate with changes in Squat, Bench, or Deadlift e1RM. "
        "Only report anatomically relevant correlations as per the system instructions. "
        "Where the exercise ROI table gives a strong |r|, use it to upgrade confidence on "
        "anatomically-plausible findings — never invent correlations from ROI alone."
    )
    return "\n".join(lines)


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
