from __future__ import annotations
from session_tool_helpers import get_store, resolve_context


async def session_replace(args: dict):
    """Full replace of a session at date+index (overwrite all fields)."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    date = args.get("date")
    index = args.get("index")
    session = args.get("session") or {}
    return await store.patch_session(program_sk, date, session, phases, index)
