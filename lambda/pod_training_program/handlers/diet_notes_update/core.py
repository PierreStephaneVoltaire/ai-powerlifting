from __future__ import annotations

from program_tool_helpers import get_store


async def diet_notes_update(args: dict) -> dict:
    notes = args.get("notes")
    if not isinstance(notes, list):
        raise ValueError("notes must be a list")
    return await get_store(args).update_diet_notes(notes, args.get("expected_revision"), args.get("idempotency_key"))
