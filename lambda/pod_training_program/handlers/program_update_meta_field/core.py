from __future__ import annotations
from program_tool_helpers import get_store

async def program_update_meta_field(args: dict):
    store = get_store(args)
    field = args.get("field")
    value = args.get("value")
    if not field:
        raise ValueError("field is required")
    await store.update_meta_field(field, value)
    return {"success": True}
