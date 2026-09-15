from __future__ import annotations
def _get_store():
    import os
    from program_store import ProgramStore as _PS
    return _PS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def _store_for(pk: str | None):
    """Return the ProgramStore singleton, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


async def health_update_current_maxes(
    args: dict | None = None,
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
    values = dict(args or {})
    updates = {
        lift: values.get(f"{lift}_kg", supplied)
        for lift, supplied in (("squat", squat_kg), ("bench", bench_kg), ("deadlift", deadlift_kg))
        if values.get(f"{lift}_kg", supplied) is not None
    }
    if not updates:
        raise ValueError("At least one max must be provided")
    store = _store_for(values.get("pk"))
    def mutate(program):
        maxes = program.setdefault("current_maxes", {})
        maxes.update(updates)
        return dict(maxes)
    return await store.mutate_source("current_maxes", updates, values.get("expected_revision"), values.get("idempotency_key"), mutate)
