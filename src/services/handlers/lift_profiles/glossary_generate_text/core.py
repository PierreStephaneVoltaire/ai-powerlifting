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


async def _dispatch(args):
    from .glossary_text_ai import generate_glossary_text
    exercise = args["exercise"]
    if not exercise.get("name"):
        raise ValueError("Exercise name is required")
    lift_profiles = args.get("lift_profiles")
    if lift_profiles is None:
        try:
            program = await _get_program_store(args).get_program()
            lift_profiles = program.get("lift_profiles", [])
        except Exception:
            lift_profiles = []
    result = await generate_glossary_text(exercise, lift_profiles=lift_profiles)
    return {"status": "generated", **result}


def glossary_generate_text(args):
    return asyncio.run(_dispatch(args))
