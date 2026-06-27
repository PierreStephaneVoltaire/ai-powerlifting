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


async def health_update_meta(updates: dict) -> dict:
    """Update program metadata fields.

    Allowed fields: program_name, comp_date, target_squat_kg, target_bench_kg,
    target_dl_kg, target_total_kg, sex, weight_class_kg, current_body_weight_kg,
    federation, practicing_for, program_start.

    Args:
        updates: Dict of field -> new value

    Returns:
        Updated meta dict

    Raises:
        ValueError: If unknown fields are passed
    """
    import copy
    allowed = {
        "program_name", "comp_date", "target_squat_kg", "target_bench_kg",
        "target_dl_kg", "target_total_kg", "sex", "weight_class_kg",
        "current_body_weight_kg", "federation", "practicing_for", "program_start",
    }
    unknown = set(updates.keys()) - allowed
    if unknown:
        raise ValueError(f"Unknown meta fields: {unknown}. Allowed: {allowed}")

    store = _get_store()
    program = await store.get_program()
    new_program = copy.deepcopy(program)

    meta = new_program.setdefault("meta", {})
    for key, value in updates.items():
        meta[key] = value

    await store._write_new_version(new_program, minor=True)
    return meta