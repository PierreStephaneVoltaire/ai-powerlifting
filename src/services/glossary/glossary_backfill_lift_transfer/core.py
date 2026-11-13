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
    from services.glossary.lift_transfer_rules import rule_lift_transfer
    store = _get_glossary_store(args)
    glossary = await store.get_glossary()
    missing = [exercise for exercise in glossary if not exercise.get("lift_transfer")]
    await store.update_exercises({exercise["id"]: {"lift_transfer": rule_lift_transfer(exercise)} for exercise in missing})
    return {
        "status": "lift_transfer_backfilled",
        "updated": len(missing),
        "total": len(glossary),
        "ai_candidates": [exercise["id"] for exercise in missing] if args.get("queue_ai") else [],
    }


def glossary_backfill_lift_transfer(args):
    return asyncio.run(_dispatch(args))
