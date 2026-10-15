from __future__ import annotations
from services.lib.session_tool_helpers import get_store, resolve_context
from services.lib.session_store import require_mutation_envelope


async def session_patch_by_date(args: dict):
    """Patch a session by date (no index - finds the matching date)."""
    require_mutation_envelope(args.get("expected_revision"), args.get("idempotency_key"))
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    date = args.get("date")
    patch = args.get("patch") or {}
    if "id" in patch or "session_id" in patch:
        raise ValueError("Session identity cannot be changed")
    extra = {key: args[key] for key in ("expected_revision", "idempotency_key") if args.get(key) is not None}
    return await store.patch_session(program_sk, date, patch, phases, None, session_id=args.get("session_id"), **extra)
