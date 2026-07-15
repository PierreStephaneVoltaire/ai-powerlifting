from __future__ import annotations
from session_tool_helpers import get_store, resolve_context


async def session_patch_by_date(args: dict):
    """Patch a session by date (no index - finds the matching date)."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    date = args.get("date")
    patch = args.get("patch") or {}
    return await store.patch_session(program_sk, date, patch, phases, None)
