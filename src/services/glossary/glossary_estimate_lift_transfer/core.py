import asyncio
import os


def _get_glossary_store(args):
    from services.runtime.glossary_store import GlossaryStore as _GS
    return _GS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


async def _dispatch(args):
    from .lift_transfer_ai import estimate_lift_transfer
    exercise_id = args.get("id")
    if not exercise_id:
        lift_transfer = await estimate_lift_transfer(args["exercise"])
        return {"status": "lift_transfer_estimated", "lift_transfer": lift_transfer}
    store = _get_glossary_store(args)
    glossary = await store.get_glossary()
    exercise = next((e for e in glossary if e["id"] == exercise_id), None)
    if not exercise:
        raise ValueError(f"Exercise not found: {exercise_id}")
    lift_transfer = await estimate_lift_transfer({**exercise, **(args.get("exercise") or {})})
    await store.update_exercise(exercise_id, {"lift_transfer": lift_transfer})
    return {"status": "lift_transfer_estimated", "id": exercise_id, "lift_transfer": lift_transfer}


def glossary_estimate_lift_transfer(args):
    return asyncio.run(_dispatch(args))
