import asyncio
import os


def _get_program_store(args):
    from program_store import ProgramStore as _PS
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
    from .muscle_group_ai import estimate_muscle_groups
    program_meta, stored_lift_profiles = await _fatigue_context(args)
    lift_profiles = args.get("lift_profiles")
    if not isinstance(lift_profiles, list) or not lift_profiles:
        lift_profiles = stored_lift_profiles
    return await estimate_muscle_groups(
        args["exercise"],
        program_meta=program_meta,
        lift_profiles=lift_profiles,
    )


def muscle_group_estimate(args):
    return asyncio.run(_dispatch(args))
