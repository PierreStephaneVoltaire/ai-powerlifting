from __future__ import annotations
from program_tool_helpers import get_store

async def program_list_full(args: dict):
    store = get_store(args)
    include = bool(args.get("include_archived", False))
    programs = await store.list_programs(include_archived=include)
    selected = args.get("program_sk")
    return [program for program in programs if not selected or program.get("sk") == selected]
