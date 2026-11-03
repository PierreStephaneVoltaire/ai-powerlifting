from __future__ import annotations

from services.lib.program_tool_helpers import get_store


async def block_notes_update(args: dict) -> dict:
    notes = args.get("block_notes")
    if not isinstance(notes, list):
        raise ValueError("block_notes must be a list")
    return await get_store(args).update_block_notes(notes, args.get("expected_revision"), args.get("idempotency_key"))
