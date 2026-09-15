from __future__ import annotations
from program_tool_helpers import get_store

async def program_update_meta_field(args: dict):
    store = get_store(args)
    updates = args.get("updates")
    if isinstance(updates, dict):
        return await store.update_meta_fields(updates, args.get("expected_revision"), args.get("idempotency_key"))
    field = args.get("field")
    value = args.get("value")
    if not field:
        raise ValueError("field is required")
    return await store.update_meta_field(field, value, args.get("expected_revision"), args.get("idempotency_key"))
