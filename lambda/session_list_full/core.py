from __future__ import annotations
from session_tool_helpers import get_store, resolve_context


async def session_list_full(args: dict):
    """List full session objects (with resolved phases) for a program."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    return await store.list_sessions(program_sk, phases)
