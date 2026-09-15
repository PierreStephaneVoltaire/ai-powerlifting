from __future__ import annotations

from program_tool_helpers import get_store


async def block_transition(args: dict) -> dict:
    store = get_store(args)
    return await store.block_transition(
        args.get("action"),
        args.get("block_id"),
        expected_revision=args.get("expected_revision"),
        idempotency_key=args.get("idempotency_key"),
        name=args.get("name"),
        current_name=args.get("current_name"),
        start_date=args.get("start_date"),
        week_start_day=args.get("week_start_day"),
        start_maxes_kg=args.get("start_maxes_kg"),
        next_program=args.get("next_program"),
    )
