from __future__ import annotations
from services.lib.session_tool_helpers import get_store, resolve_context
from services.lib.session_store import require_mutation_envelope


async def session_replace_all(args: dict):
    """Replace ALL sessions for a program (delete existing, write incoming)."""
    require_mutation_envelope(args.get("expected_revision"), args.get("idempotency_key"))
    store = get_store(args)
    program_sk, phases = await resolve_context(store, args.get("program_sk"))
    sessions = args.get("sessions") or []
    extra = {key: args[key] for key in ("expected_revision", "idempotency_key") if args.get(key) is not None}
    result = await store.replace_program_sessions(program_sk, sessions, phases, **extra)
    return result or {"success": True}
