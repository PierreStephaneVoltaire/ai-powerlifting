import asyncio
import os


def _get_program_store(args):
    from program_store import ProgramStore as _PS
    _program_store = _PS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _program_store


def _get_glossary_store(args):
    from glossary_store import GlossaryStore as _GS
    _glossary_store = _GS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )
    return _glossary_store


async def _dispatch(args):
    from .fatigue_ai import estimate_fatigue_profile
    exercise_id = args["id"]
    glossary = await _get_glossary_store(args).get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")
    program = await _get_program_store(args).get_program()
    profile = await estimate_fatigue_profile(
        ex,
        program_meta=program.get("meta", {}),
        lift_profiles=program.get("lift_profiles", []),
    )
    fatigue_profile = {
        "axial": profile.get("axial"),
        "neural": profile.get("neural"),
        "peripheral": profile.get("peripheral"),
        "systemic": profile.get("systemic"),
    }
    await _get_glossary_store(args).update_exercise(
        exercise_id,
        {
            "fatigue_profile": fatigue_profile,
            "fatigue_profile_source": "ai_estimated",
            "fatigue_profile_reasoning": profile.get("reasoning"),
        },
    )
    return {
        "status": "fatigue_estimated",
        "id": exercise_id,
        "profile": profile,
        "fatigue_profile": fatigue_profile,
        "reasoning": profile.get("reasoning"),
    }


def glossary_estimate_fatigue(args):
    return asyncio.run(_dispatch(args))
