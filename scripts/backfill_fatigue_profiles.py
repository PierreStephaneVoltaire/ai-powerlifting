"""Backfill fatigue profiles for all glossary exercises that don't have one.

Usage:
    python scripts/backfill_fatigue_profiles.py [--dry-run] [--exercise "Barbell Row"]

Requires: OPENROUTER_API_KEY env var
"""
import argparse
import asyncio
import json
import os
import time

import boto3
import httpx

TABLE_NAME = os.getenv("IF_HEALTH_TABLE_NAME", "if-health")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
BACKFILL_MODEL = os.getenv("BACKFILL_FATIGUE_PROFILE_MODEL", "anthropic/claude-sonnet-4-6")
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

_SYSTEM_PROMPT = """\
You are a sports science expert estimating fatigue profiles for resistance training exercises.

For each exercise, estimate 4 fatigue dimensions on a 0.0-1.0 scale:

1. **Axial** (0.0-1.0): Spinal compression loading. How much compressive force goes through the spine.
   - Squats/Deadlifts: 0.7-0.9
   - Overhead press: 0.4-0.6
   - Bench press: 0.1-0.3
   - Isolation exercises: 0.0-0.1

2. **Neural** (0.0-1.0): Central nervous system demand baseline (before intensity scaling).
   - Heavy compounds near 1RM: 0.7-0.9
   - Moderate compounds: 0.4-0.6
   - Machine/isolation: 0.1-0.3
   - Cardio-only movements: 0.0-0.1

3. **Peripheral** (0.0-1.0): Local muscle damage potential. How much muscle tissue is stressed.
   - Big compound movements: 0.6-0.8
   - Medium compounds: 0.4-0.6
   - Isolation: 0.3-0.5
   - Bodyweight/rehab: 0.1-0.3

4. **Systemic** (0.0-1.0): Cardiovascular/metabolic demand.
   - Deadlifts: 0.7-0.9
   - Squats: 0.5-0.7
   - Upper body compounds: 0.3-0.5
   - Isolation: 0.1-0.3

Calibration anchors:
- Competition squat: axial=0.85, neural=0.80, peripheral=0.75, systemic=0.60
- Competition bench: axial=0.20, neural=0.70, peripheral=0.65, systemic=0.35
- Competition deadlift: axial=0.90, neural=0.90, peripheral=0.80, systemic=0.80
- Bicep curl: axial=0.00, neural=0.10, peripheral=0.40, systemic=0.10
- Face pulls: axial=0.00, neural=0.05, peripheral=0.25, systemic=0.05

Rules:
- Round all values to nearest 0.05
- Consider equipment, muscles involved, and movement pattern
- Provide brief reasoning for the estimate
"""

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_fatigue_profile",
        "description": "Estimate 4-dimensional fatigue profile for an exercise",
        "parameters": {
            "type": "object",
            "properties": {
                "axial": {"type": "number"},
                "neural": {"type": "number"},
                "peripheral": {"type": "number"},
                "systemic": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["axial", "neural", "peripheral", "systemic", "reasoning"],
        },
    },
}


def _round_to_nearest(value: float, step: float = 0.05) -> float:
    return round(round(value / step) * step, 2)


def _build_user_message(exercise: dict) -> str:
    parts = [f"Exercise: {exercise.get('name', 'Unknown')}"]
    if exercise.get("category"):
        parts.append(f"Category: {exercise['category']}")
    if exercise.get("equipment"):
        parts.append(f"Equipment: {exercise['equipment']}")
    if exercise.get("primary_muscles"):
        parts.append(f"Primary muscles: {', '.join(exercise['primary_muscles'])}")
    if exercise.get("secondary_muscles"):
        parts.append(f"Secondary muscles: {', '.join(exercise['secondary_muscles'])}")
    if exercise.get("cues"):
        parts.append(f"Cues: {', '.join(exercise['cues'])}")
    if exercise.get("notes"):
        parts.append(f"Notes: {exercise['notes']}")
    return "\n".join(parts)


async def estimate_fatigue_profile(exercise: dict) -> dict:
    """Call LLM to estimate 4-dimensional fatigue profile for an exercise."""
    user_msg = _build_user_message(exercise)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": BACKFILL_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "tools": [_TOOL_SCHEMA],
                "tool_choice": {"type": "function", "function": {"name": "estimate_fatigue_profile"}},
            },
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        raise ValueError("No choices in LLM response")

    tool_calls = choices[0].get("message", {}).get("tool_calls", [])
    if not tool_calls:
        raise ValueError("No tool calls in LLM response")

    args = json.loads(tool_calls[0]["function"]["arguments"])
    return {
        "axial": _round_to_nearest(float(args.get("axial", 0.3))),
        "neural": _round_to_nearest(float(args.get("neural", 0.3))),
        "peripheral": _round_to_nearest(float(args.get("peripheral", 0.5))),
        "systemic": _round_to_nearest(float(args.get("systemic", 0.3))),
        "reasoning": args.get("reasoning", ""),
    }


def get_glossary(table):
    resp = table.get_item(Key={"pk": "operator", "sk": "glossary#v1"})
    item = resp.get("Item")
    if not item:
        return []
    return item.get("exercises", [])


def save_glossary(table, exercises):
    table.put_item(Item={
        "pk": "operator",
        "sk": "glossary#v1",
        "exercises": exercises,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


async def backfill(dry_run=False, exercise_name=None):
    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(TABLE_NAME)
    exercises = get_glossary(table)
    updated = False

    for ex in exercises:
        if exercise_name and ex.get("name") != exercise_name:
            continue
        if ex.get("fatigue_profile") and ex.get("fatigue_profile_source") == "manual":
            print(f"SKIP (manual): {ex['name']}")
            continue

        print(f"Estimating: {ex.get('name', '???')}...")
        try:
            profile = await estimate_fatigue_profile(ex)
        except Exception as e:
            print(f"  -> ERROR: {e}")
            continue

        if dry_run:
            print(f"  -> {json.dumps(profile, indent=2)}")
        else:
            ex["fatigue_profile"] = {k: profile[k] for k in ["axial", "neural", "peripheral", "systemic"]}
            ex["fatigue_profile_source"] = "ai_estimated"
            ex["fatigue_profile_reasoning"] = profile.get("reasoning")
            updated = True
            print(f"  -> Saved profile for {ex['name']}")

        time.sleep(1)

    if not dry_run and updated:
        save_glossary(table, exercises)
        print(f"Saved {len(exercises)} exercises")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill fatigue profiles for glossary exercises")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--exercise", type=str, default=None, help="Target a single exercise by name")
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run, exercise_name=args.exercise))
