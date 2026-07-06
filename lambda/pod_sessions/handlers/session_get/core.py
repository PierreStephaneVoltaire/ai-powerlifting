from __future__ import annotations
import asyncio
from session_tool_helpers import get_store, resolve_context
from session_store import _public_session


async def session_get(args: dict):
    """Load a single session by date (+index for same-day ordinals)."""
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    date = args.get("date")
    index = args.get("index")
    loop = asyncio.get_running_loop()
    item = await loop.run_in_executor(None, lambda: store._find_item_sync(program_sk, date, index))
    return _public_session(item, phases)
