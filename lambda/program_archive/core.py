from __future__ import annotations
from program_tool_helpers import get_store

async def program_archive(args: dict):
    store = get_store(args)
    sk = args.get("program_sk")
    if not sk:
        sk = store._current_program_sk_sync()
    await store.archive(sk)
    return {"success": True}
