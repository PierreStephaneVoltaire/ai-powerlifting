from __future__ import annotations
import asyncio
from decimal import Decimal
from services.lib.program_tool_helpers import get_store
from services.lib.competition_entries import with_competition_entries
from services.lib.block_scope import ALL_BLOCKS, scope_program


def _coerce_decimals(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 != 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _coerce_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_decimals(v) for v in obj]
    return obj


async def program_get(args: dict):
    store = args.get("_store") or get_store(args)
    program = await store.get_program()
    program_sk = None
    if hasattr(store, "_current_program_sk_sync"):
        program_sk = await asyncio.get_running_loop().run_in_executor(
            None, store._current_program_sk_sync
        )
    block = args.get("block")
    window_start = args.get("window_start")
    window_end = args.get("window_end")
    program = await asyncio.to_thread(
        with_competition_entries,
        program,
        store.pk,
        start=window_start,
        end=window_end,
    )
    if block and block != ALL_BLOCKS:
        program = scope_program(program, block)
    if program_sk is not None and hasattr(store, "_get_session_store"):
        from services.lib.block_scope import current_block_id
        active_block = current_block_id(program)
        program["sessions"] = await store._get_session_store().list_sessions(
            str(program_sk),
            program.get("phases", []) if isinstance(program.get("phases"), list) else [],
            window_start=window_start,
            window_end=window_end,
            block_id=block if block and block != ALL_BLOCKS else None,
            active_block_id=active_block,
        )
    return _coerce_decimals(program)
