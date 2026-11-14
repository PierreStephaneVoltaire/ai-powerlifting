import asyncio
import os


async def _athlete_meta(args):
    if not args.get("pk"):
        return None
    try:
        from services.runtime.program_store import ProgramStore
        store = ProgramStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=args["pk"],
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        program = await store.get_program()
    except Exception:
        return None
    return program.get("meta") if isinstance(program, dict) else None


async def _dispatch(args):
    from services.lift_profiles.lift_profile_ai import estimate_stimulus
    return await estimate_stimulus(args["profile"], athlete_meta=await _athlete_meta(args))


def lift_profile_estimate_stimulus(args):
    return asyncio.run(_dispatch(args))
