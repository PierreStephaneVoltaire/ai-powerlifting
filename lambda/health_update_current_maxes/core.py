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


async def health_update_current_maxes(
    squat_kg: float | None = None,
    bench_kg: float | None = None,
    deadlift_kg: float | None = None,
) -> dict:
    """Update current competition maxes.

    Args:
        squat_kg: New squat max in kg (omit to leave unchanged)
        bench_kg: New bench max in kg (omit to leave unchanged)
        deadlift_kg: New deadlift max in kg (omit to leave unchanged)

    Returns:
        Updated current_maxes dict

    Raises:
        ValueError: If no fields provided
    """
    import copy
    if squat_kg is None and bench_kg is None and deadlift_kg is None:
        raise ValueError("At least one max must be provided")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    maxes = new_program.setdefault("current_maxes", {})
    if squat_kg is not None:
        maxes["squat"] = squat_kg
    if bench_kg is not None:
        maxes["bench"] = bench_kg
    if deadlift_kg is not None:
        maxes["deadlift"] = deadlift_kg

    await store._write_new_version(new_program, minor=True)
    return maxes