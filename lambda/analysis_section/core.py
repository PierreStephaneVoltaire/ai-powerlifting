"""Lambda core for analysis_section — replicates tools/health/tool.py dispatcher.

Loads program+sessions via the ProgramStore layer, fetches glossary via direct
DynamoDB, then computes a single deterministic weekly analysis section via the
analytics module (copied verbatim from tools/health/analytics.py).

AI section keys (ai_correlation, program_evaluation) are rejected by the
handler before reaching this core.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _sanitize_decimals(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_decimals(v) for v in obj]
    return obj


def _get_glossary_sync(table_name: str) -> list[dict]:
    """Fetch glossary from DynamoDB for the active health partition."""
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": _get_store().pk, "sk": "glossary#v1"})
    item = resp.get("Item")
    if not item:
        return []
    return _sanitize_decimals(item.get("exercises", []))


def _get_program_and_sessions(refresh_program: bool = False):
    """Fetch program from store, return (program, sessions, program_start)."""
    store = _get_store()
    if refresh_program:
        store.invalidate_cache()
    program = _run_async(store.get_program())
    sessions = program.get("sessions", [])
    program_start = program.get("meta", {}).get("program_start", "")
    return program, sessions, program_start


def _get_analysis_program_and_sessions(args: dict, refresh_program: bool = False):
    """Use caller-supplied snapshots when available; otherwise load from the store."""
    supplied_program = args.get("program")
    supplied_sessions = args.get("sessions")
    if isinstance(supplied_program, dict):
        program = dict(supplied_program)
        sessions = supplied_sessions if isinstance(supplied_sessions, list) else program.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        program["sessions"] = sessions
        program_start = program.get("meta", {}).get("program_start", "")
        return program, sessions, program_start

    return _get_program_and_sessions(refresh_program=refresh_program)


def analysis_section(args: dict) -> dict:
    """Replicates _do_analysis_section from tools/health/tool.py."""
    from analytics import weekly_analysis_section
    from config import IF_HEALTH_TABLE_NAME
    program, sessions, program_start = _get_analysis_program_and_sessions(
        args,
        refresh_program=args.get("refresh_program", True),
    )
    glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME)
    return weekly_analysis_section(
        program,
        sessions,
        section=args["section"],
        window_start=args.get("window_start"),
        window_end=args.get("window_end"),
        ref_date=args.get("ref_date"),
        week_start=args.get("week_start"),
        week_end=args.get("week_end"),
        weeks=args.get("weeks", 1),
        block=args.get("block", "current"),
        glossary=glossary,
    )