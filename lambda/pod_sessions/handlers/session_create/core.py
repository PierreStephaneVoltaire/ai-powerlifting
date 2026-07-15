from __future__ import annotations
from session_tool_helpers import get_store, resolve_context


async def session_create(args: dict):
    """Create a new session for the current program."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    session = args.get("session") or {}
    return await store.create_session(program_sk, session, phases)
