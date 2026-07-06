from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


async def calculate_attempts(
    lift: str,
    opener_kg: float,
    j1_override: float | None = None,
    j2_override: float | None = None,
    last_felt: str | None = None,
) -> dict:
    """Calculate competition attempts based on program preferences.

    Args:
        lift: "squat", "bench", or "deadlift"
        opener_kg: First attempt weight in kg
        j1_override: Override jump 1 from program prefs (optional)
        j2_override: Override jump 2 from program prefs (optional)
        last_felt: "hard" to halve j2 (optional)

    Returns:
        {
            "lift": "squat",
            "attempt_1_kg": 160.0,
            "attempt_2_kg": 180.0,
            "attempt_3_kg": 200.0,
            "jumps_used": {"j1": 20, "j2": 20},
            "warnings": ["Attempt 3 exceeds current max..."]
        }

    Raises:
        ValueError: If lift not in valid list
    """
    valid_lifts = ["squat", "bench", "deadlift"]
    if lift not in valid_lifts:
        raise ValueError(f"Invalid lift: {lift}. Must be one of {valid_lifts}")

    store = _get_store()
    program = await store.get_program()

    operator_prefs = program.get("operator_prefs", {})
    attempt_jumps = operator_prefs.get("attempt_jumps", {})
    lift_jumps = attempt_jumps.get(lift, {"j1": 10, "j2": 10})

    j1 = j1_override if j1_override is not None else lift_jumps.get("j1", 10)
    j2 = j2_override if j2_override is not None else lift_jumps.get("j2", 10)

    if last_felt == "hard":
        j2 = round(j2 / 2 / 2.5) * 2.5

    attempt_1 = opener_kg
    attempt_2 = round((attempt_1 + j1) / 2.5) * 2.5
    attempt_3 = round((attempt_2 + j2) / 2.5) * 2.5

    current_maxes = program.get("current_maxes", {})
    current_max = current_maxes.get(lift)

    warnings = []

    if current_max:
        min_opener = current_max * 0.7
        if opener_kg < min_opener:
            warnings.append(
                f"Opener {opener_kg}kg is below 70% of current max ({current_max}kg). "
                f"Consider an opener of at least {round(min_opener / 2.5) * 2.5}kg."
            )

        if attempt_3 > current_max:
            warnings.append(
                f"Attempt 3 ({attempt_3}kg) exceeds current max of {current_max}kg — "
                "confirm this is a target PR."
            )

    return {
        "lift": lift,
        "attempt_1_kg": attempt_1,
        "attempt_2_kg": attempt_2,
        "attempt_3_kg": attempt_3,
        "jumps_used": {"j1": j1, "j2": j2},
        "warnings": warnings,
    }