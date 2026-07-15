from __future__ import annotations
from program_tool_helpers import get_store

async def program_update_phases(args: dict):
    store = get_store(args)
    phases = args.get("phases") or []
    block = args.get("block")
    await store.update_phases(phases, block)
    return {"success": True}
