import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_program_store: Optional[object] = None
_glossary_store: Optional[object] = None


def _get_program_store():
    global _program_store
    if _program_store is None:
        from program_store import ProgramStore as _PS
        _program_store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _program_store


def _get_glossary_store():
    global _glossary_store
    if _glossary_store is None:
        from glossary_store import GlossaryStore as _GS
        _glossary_store = _GS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _glossary_store


async def _dispatch(args):
    from .fatigue_ai import estimate_fatigue_profile
    exercise_id = args["id"]
    glossary = await _get_glossary_store().get_glossary()
    ex = next((e for e in glossary if e["id"] == exercise_id), None)
    if not ex:
        raise ValueError(f"Exercise not found: {exercise_id}")
    program = await _get_program_store().get_program()
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
    await _get_glossary_store().update_exercise(
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


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_dispatch(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}