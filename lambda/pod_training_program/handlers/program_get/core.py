from __future__ import annotations
from program_tool_helpers import get_store

async def program_get(args: dict):
    store = get_store(args)
    return await store.get_program()
