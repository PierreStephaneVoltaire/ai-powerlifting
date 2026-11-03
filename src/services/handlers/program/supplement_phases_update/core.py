from __future__ import annotations

from services.lib.program_tool_helpers import get_store


async def supplement_phases_update(args: dict) -> dict:
    phases = args.get("phases")
    if not isinstance(phases, list):
        raise ValueError("phases must be a list")
    return await get_store(args).update_supplement_phases(phases, args.get("expected_revision"), args.get("idempotency_key"))
