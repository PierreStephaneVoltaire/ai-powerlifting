import asyncio
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_store: Optional[object] = None


def _get_program_store():
    global _store
    if _store is None:
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _store


async def _fatigue_context():
    try:
        program = await _get_program_store().get_program()
    except Exception:
        return None, None
    if not isinstance(program, dict):
        return None, None
    return program.get("meta") or None, program.get("lift_profiles") or None


async def _dispatch(args):
    from muscle_group_ai import estimate_muscle_groups
    program_meta, stored_lift_profiles = await _fatigue_context()
    lift_profiles = args.get("lift_profiles")
    if not isinstance(lift_profiles, list) or not lift_profiles:
        lift_profiles = stored_lift_profiles
    return await estimate_muscle_groups(
        args["exercise"],
        program_meta=program_meta,
        lift_profiles=lift_profiles,
    )


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_dispatch(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}