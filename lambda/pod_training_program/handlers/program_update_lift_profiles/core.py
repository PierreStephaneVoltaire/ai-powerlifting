from __future__ import annotations
from program_tool_helpers import get_store

async def program_update_lift_profiles(args: dict):
    store = get_store(args)
    profiles = args.get("lift_profiles") or args.get("profiles") or []
    await store.update_lift_profiles(profiles)
    return {"success": True}
