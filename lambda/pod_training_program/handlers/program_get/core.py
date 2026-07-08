from __future__ import annotations
import asyncio
from program_tool_helpers import get_store


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return float(value) if value % 1 > 0 else int(value)
        f = float(value)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return None


def _coerce_current_maxes(program: dict) -> dict:
    maxes = program.get("current_maxes")
    if isinstance(maxes, dict):
        program["current_maxes"] = {k: _to_number(v) for k, v in maxes.items()}
    return program


async def program_get(args: dict):
    store = get_store(args)
    program = await store.get_program()
    program_sk = await asyncio.get_running_loop().run_in_executor(
        None, store._current_program_sk_sync
    )
    program["sessions"] = await store._get_session_store().list_sessions(
        str(program_sk),
        program.get("phases", []) if isinstance(program.get("phases"), list) else [],
    )
    return _coerce_current_maxes(program)
