import asyncio
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
    from .fatigue_ai import estimate_fatigue_profile
    program_meta, lift_profiles = await _fatigue_context()
    return await estimate_fatigue_profile(
        args["exercise"],
        program_meta=program_meta,
        lift_profiles=lift_profiles,
    )


def fatigue_profile_estimate(args):
    return asyncio.run(_dispatch(args))
