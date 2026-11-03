import asyncio
import os


def _get_program_store(args):
    from services.lib.program_store import ProgramStore as _PS
    _store = _PS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _store


async def _fatigue_context(args):
    try:
        program = await _get_program_store(args).get_program()
    except Exception:
        return None, None
    if not isinstance(program, dict):
        return None, None
    return program.get("meta") or None, program.get("lift_profiles") or None


async def _dispatch(args):
    from .fatigue_ai import estimate_fatigue_profile
    program_meta, lift_profiles = await _fatigue_context(args)
    return await estimate_fatigue_profile(
        args["exercise"],
        program_meta=program_meta,
        lift_profiles=lift_profiles,
    )


def fatigue_profile_estimate(args):
    return asyncio.run(_dispatch(args))
