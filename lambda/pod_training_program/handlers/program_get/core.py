from __future__ import annotations
import asyncio
from program_tool_helpers import get_store


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
    return program
