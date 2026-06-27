"""Lambda core for regenerate_analysis — replicates tools/health/tool.py dispatcher.

Regenerates deterministic current-block analysis caches and markdown export.
AI reports are intentionally excluded. NEVER touches past-block caches.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None
_glossary_store: Optional[Any] = None


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


def _get_glossary_store():
    global _glossary_store
    if _glossary_store is None:
        import os
        from glossary_store import GlossaryStore
        _glossary_store = GlossaryStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _glossary_store


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


def _floats_to_decimals(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    from decimal import Decimal
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj


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


def _build_sectioned_week_analysis(
    program: dict,
    sessions: list[dict],
    glossary: list[dict] | None,
    *,
    week_start: int,
    week_end: int,
    ref_date: str,
) -> dict:
    return _build_sectioned_analysis(
        program,
        sessions,
        glossary,
        weeks=max(1, week_end - week_start + 1),
        block="current",
        week_start=week_start,
        week_end=week_end,
        ref_date=ref_date,
    )


def _scope_program_to_current_block(program: dict) -> dict:
    """Return a shallow copy of program with phases and sessions filtered to the current block only."""
    scoped = dict(program)
    scoped["phases"] = [p for p in program.get("phases", []) if (p.get("block") or "current") == "current"]
    scoped["sessions"] = [s for s in program.get("sessions", []) if (s.get("block") or "current") == "current"]
    return scoped


async def regenerate_analysis(args: Dict[str, Any]) -> Dict[str, Any]:
    """Regenerate deterministic current-block analysis caches and markdown export.

    AI reports are intentionally excluded; they are regenerated only through
    explicit AI section tools because those calls are comparatively expensive.
    NEVER touches past-block caches.
    """
    import os
    import tempfile
    import boto3
    from export import build_program_markdown

    from config import ANALYSIS_CACHE_TABLE_NAME, AWS_REGION

    store = _get_store()
    store.invalidate_cache()
    program = await store.get_program()
    pk = store.pk
    sessions = program.get("sessions", [])
    glossary = _run_async(_get_glossary_store().get_glossary()) if hasattr(_get_glossary_store(), "get_glossary") else []

    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(ANALYSIS_CACHE_TABLE_NAME)
    cache_pk = f"analysis#{pk}"
    expires_at = int(_time.time()) + 7 * 86400

    program_start = (program.get("meta") or {}).get("program_start") or next(
        (s.get("date") for s in sessions if (s.get("block") or "current") == "current"), None
    ) or datetime.utcnow().date().isoformat()

    current_sessions = [s for s in sessions if (s.get("block") or "current") == "current"]
    current_week = max(
        (int(s.get("week_number", 0)) for s in current_sessions if s.get("week_number")),
        default=1
    )

    window_specs = [
        ("current", current_week, current_week),
        ("previous_1", max(1, current_week - 1), current_week),
        ("previous_2", max(1, current_week - 2), current_week),
        ("previous_4", max(1, current_week - 4), current_week),
        ("previous_8", max(1, current_week - 8), current_week),
        ("block", 1, current_week),
    ]

    today_iso = datetime.utcnow().date().isoformat()
    errors = []
    block_analysis_result = None

    for window_key, week_start, week_end in window_specs:
        try:
            result = _build_sectioned_week_analysis(
                program,
                sessions,
                glossary,
                week_start=week_start,
                week_end=week_end,
                ref_date=today_iso,
            )
            if window_key == "block":
                block_analysis_result = result

            payload_str = json.dumps(result)
            sk = f"weekly_analysis#{window_key}"
            item = {
                "pk": cache_pk,
                "sk": sk,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": expires_at,
                "payload": payload_str,
            }
            table.put_item(Item=_floats_to_decimals(item))
        except Exception as exc:
            errors.append(f"window {window_key}: {exc}")

    try:
        out_path = os.path.join(tempfile.gettempdir(), "program_history_regen.md")
        scoped_program = _scope_program_to_current_block(program)
        analysis_bundle = {
            "weekly": block_analysis_result or {},
            "pk": pk,
            "sex": str((program.get("meta") or {}).get("sex") or "male").lower(),
        }
        build_program_markdown(scoped_program, out_path, analysis=analysis_bundle, export_context=analysis_bundle)
        with open(out_path, "r", encoding="utf-8") as f:
            markdown = f.read()
        if markdown:
            md_item = {
                "pk": cache_pk,
                "sk": "markdown_export#current",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "expires_at": expires_at,
                "payload": json.dumps({"markdown": markdown}),
            }
            table.put_item(Item=_floats_to_decimals(md_item))
            try:
                from cache_invalidation import clear_markdown_export_dirty
                clear_markdown_export_dirty(pk, ANALYSIS_CACHE_TABLE_NAME, AWS_REGION)
            except Exception:
                pass
    except Exception as exc:
        errors.append(f"markdown_export: {exc}")

    return {
        "success": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "windows_regenerated": 6,
        "errors": errors,
        "message": (
            f"Regenerated 6 deterministic analysis windows from individual section calculations and markdown export. AI reports were not regenerated."
            + (f" {len(errors)} non-fatal errors: {'; '.join(errors)}" if errors else "")
        ),
    }