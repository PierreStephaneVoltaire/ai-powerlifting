from __future__ import annotations
from program_tool_helpers import get_store

async def program_list_full(args: dict):
    store = get_store(args)
    include = bool(args.get("include_archived", False))
    return await store.list_programs(include_archived=include)
