from __future__ import annotations
from session_tool_helpers import get_store, resolve_context


async def session_replace_all(args: dict):
    """Replace ALL sessions for a program (delete existing, write incoming)."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    sessions = args.get("sessions") or []
    await store.replace_program_sessions(program_sk, sessions, phases)
    return {"success": True}
