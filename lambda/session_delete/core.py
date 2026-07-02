from __future__ import annotations
from session_tool_helpers import get_store, resolve_context


async def session_delete(args: dict):
    """Delete a session at date+index."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    date = args.get("date")
    index = args.get("index")
    return await store.delete_session(program_sk, date, index)
