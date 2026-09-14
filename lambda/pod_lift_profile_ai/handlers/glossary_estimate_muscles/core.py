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
    from .muscle_group_ai import estimate_muscle_groups
    exercise_id = args["id"]
    glossary = await _get_glossary_store(args).get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")
    program = await _get_program_store(args).get_program()
    estimate = await estimate_muscle_groups(
        ex,
        program_meta=program.get("meta", {}),
        lift_profiles=program.get("lift_profiles", []),
    )
    primary_muscles = estimate.get("primary_muscles", [])
    secondary_muscles = estimate.get("secondary_muscles", [])
    tertiary_muscles = estimate.get("tertiary_muscles", [])
    await _get_glossary_store(args).update_exercise(
        exercise_id,
        {
            "primary_muscles": primary_muscles,
            "secondary_muscles": secondary_muscles,
            "tertiary_muscles": tertiary_muscles,
        },
    )
    return {
        "status": "muscles_estimated",
        "id": exercise_id,
        "primary_muscles": primary_muscles,
        "secondary_muscles": secondary_muscles,
        "tertiary_muscles": tertiary_muscles,
        "reasoning": estimate.get("reasoning", ""),
    }


def glossary_estimate_muscles(args):
    return asyncio.run(_dispatch(args))
