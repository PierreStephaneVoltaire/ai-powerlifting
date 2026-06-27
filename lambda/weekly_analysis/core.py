"""Lambda core for weekly_analysis — replicates tools/health/tool.py dispatcher.

Loads program+sessions via the ProgramStore layer, fetches glossary via direct
DynamoDB, then builds a sectioned deterministic weekly analysis via the
analytics module (copied verbatim from tools/health/analytics.py).

AI sections (program_evaluation, correlation) are intentionally omitted.
"""
from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

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


_DETERMINISTIC_ANALYSIS_SECTIONS = ["overview", "fatigue_readiness", "peaking", "workload", "alerts"]


def _build_sectioned_analysis(
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None,
    *,
    weeks: int = 1,
    block: str = "current",
    window_start: str | None = None,
    window_end: str | None = None,
    ref_date: str | None = None,
    week_start: int | None = None,
    week_end: int | None = None,
) -> dict:
    from analytics import weekly_analysis_section

    result: dict[str, Any] = {}
    for section in _DETERMINISTIC_ANALYSIS_SECTIONS:
        result.update(weekly_analysis_section(
            program=program,
            sessions=sessions,
            section=section,
            weeks=weeks,
            block=block,
            window_start=window_start,
            window_end=window_end,
            week_start=week_start,
            week_end=week_end,
            ref_date=ref_date,
            glossary=glossary,
        ))
    return result


def weekly_analysis(args: dict) -> dict:
    """Replicates _do_weekly_analysis from tools/health/tool.py."""
    from config import IF_HEALTH_TABLE_NAME
    program, sessions, program_start = _get_analysis_program_and_sessions(
        args,
        refresh_program=args.get("refresh_program", True),
    )
    glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME)
    return _build_sectioned_analysis(
        program,
        sessions,
        glossary,
        weeks=args.get("weeks", 1),
        block=args.get("block", "current"),
        window_start=args.get("window_start"),
        window_end=args.get("window_end"),
        ref_date=args.get("ref_date"),
        week_start=args.get("week_start"),
        week_end=args.get("week_end"),
    )