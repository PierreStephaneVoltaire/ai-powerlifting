from __future__ import annotations
from services.lib.session_tool_helpers import get_store, resolve_context
from services.lib.session_store import require_mutation_envelope


async def session_create(args: dict):
    """Create a new session for the current program."""
    require_mutation_envelope(args.get("expected_revision"), args.get("idempotency_key"))
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    session = args.get("session") or {}
    extra = {key: args[key] for key in ("expected_revision", "idempotency_key") if args.get(key) is not None}
    return await store.create_session(program_sk, session, phases, **extra)
