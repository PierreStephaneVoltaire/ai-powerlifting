from __future__ import annotations
from session_tool_helpers import get_store, resolve_context
from session_store import require_mutation_envelope


async def session_replace(args: dict):
    """Full replace of a session at date+index (overwrite all fields)."""
    require_mutation_envelope(args.get("expected_revision"), args.get("idempotency_key"))
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    date = args.get("date")
    index = args.get("index")
    session = args.get("session") or {}
    extra = {key: args[key] for key in ("expected_revision", "idempotency_key") if args.get(key) is not None}
    return await store.patch_session(program_sk, date, session, phases, index, session_id=args.get("session_id") or session.get("id"), **extra)
