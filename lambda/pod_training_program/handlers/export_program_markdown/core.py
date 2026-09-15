"""Lambda core for export_program_markdown — replicates tools/health/tool.py dispatcher.

Generates a markdown export of the current program and returns its content.
AI section calls (program_evaluation) are intentionally omitted from the
analysis bundle; correlation uses cached DynamoDB values only.
"""
from __future__ import annotations

import asyncio
import logging
from importlib import import_module
from competition_entries import with_competition_entries
import os
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store(args):
    """Lazily create and return the ProgramStore singleton."""
    import os
    from program_store import ProgramStore as _PS
    _store = _PS(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=args["pk"],
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


def _get_glossary_sync(table_name: str, pk: str) -> list[dict]:
    """Fetch glossary from DynamoDB for the active health partition."""
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": pk, "sk": "glossary#v1"})
    item = resp.get("Item")
    if not item:
        return []
    return _sanitize_decimals(item.get("exercises", []))


def _get_versioned_item_sync(table_name: str, pk: str, sk: str) -> dict | None:
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": pk, "sk": sk})
    item = resp.get("Item")
    if not item:
        return None
    return _sanitize_decimals(item)


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
    from .analytics import weekly_analysis_section

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


def _read_cached_correlation(pk: str, weeks: int = 4) -> dict | None:
    """Return the cached correlation report for the current window, or None."""
    import boto3
    from .config import IF_HEALTH_TABLE_NAME

    today = datetime.utcnow().date()
    raw_cutoff = today - timedelta(weeks=weeks)
    window_start = (raw_cutoff - timedelta(days=raw_cutoff.weekday())).isoformat()
    cache_sk = f"corr_report#{window_start}_{weeks}w"

    table = boto3.resource("dynamodb", region_name="ca-central-1").Table(IF_HEALTH_TABLE_NAME)
    item = table.get_item(Key={"pk": pk, "sk": cache_sk}).get("Item")
    if not item or not item.get("report"):
        return None

    report = item["report"]
    if isinstance(report, dict):
        report["cached"] = True
        report["generated_at"] = item.get("generated_at", "")
        report["window_start"] = window_start
        report["weeks"] = weeks
    return _sanitize_decimals(report)


def _build_analysis_bundle(program: dict, sessions: list[dict], store) -> dict:
    """Assemble the analysis bundle threaded into the markdown export.

    Uses cached AI reports (no forced regeneration) and the pure weekly_analysis
    function. Missing pieces degrade gracefully.

    NOTE: program_evaluation AI call is omitted in the lambda (AI-excluded).
    """
    from .config import IF_HEALTH_TABLE_NAME
    from .prompt_context import summarize_lift_profiles

    active_pk = store.pk
    cache_version = getattr(store, "_cache_version", None)
    version_token = f"v{int(cache_version):03d}" if isinstance(cache_version, int) and cache_version > 0 else ""

    bundle: dict[str, Any] = {
        "weekly": None,
        "correlation": None,
        "program_evaluation": None,
        "lift_profiles": summarize_lift_profiles(program.get("lift_profiles")),
        "pk": active_pk,
        "version": version_token,
        "sex": str((program.get("meta") or {}).get("sex") or "male").lower(),
    }

    try:
        glossary = _get_glossary_sync(IF_HEALTH_TABLE_NAME, active_pk)
    except Exception as e:
        logger.warning("export: glossary fetch failed (%s); continuing without it", e)
        glossary = []

    bundle["glossary"] = glossary

    try:
        bundle["federation_library"] = _get_versioned_item_sync(IF_HEALTH_TABLE_NAME, active_pk, "federations#v1") or {
            "pk": active_pk,
            "sk": "federations#v1",
            "updated_at": "",
            "federations": [],
            "qualification_standards": [],
        }
    except Exception as e:
        logger.warning("export: federation library fetch failed (%s); continuing without it", e)
        bundle["federation_library"] = {
            "pk": active_pk,
            "sk": "federations#v1",
            "updated_at": "",
            "federations": [],
            "qualification_standards": [],
        }

    try:
        if version_token:
            weight_log_item = _get_versioned_item_sync(IF_HEALTH_TABLE_NAME, active_pk, f"weight_log#{version_token}")
            bundle["weight_log"] = (weight_log_item or {}).get("entries", [])
        else:
            bundle["weight_log"] = []
    except Exception as e:
        logger.warning("export: weight log fetch failed (%s); continuing without it", e)
        bundle["weight_log"] = []

    try:
        if version_token:
            max_history_item = _run_async(import_module("lambda.pod_maxes.handlers.max_history_get.core").max_history_get({"pk": active_pk, "version": version_token, "_access": getattr(store, "export_access", None) or {}}))
            bundle["max_history"] = (max_history_item or {}).get("entries", [])
        else:
            bundle["max_history"] = []
    except Exception as e:
        logger.warning("export: max history fetch failed (%s); continuing without it", e)
        bundle["max_history"] = []

    try:
        block_sessions = [s for s in sessions if s.get("block", "current") == "current" and s.get("date")]
        if not block_sessions:
            effective_weeks = 4
        else:
            block_sessions.sort(key=lambda x: x["date"])
            first = datetime.fromisoformat(block_sessions[0]["date"][:10])
            last = datetime.fromisoformat(block_sessions[-1]["date"][:10])
            diff_days = abs((last - first).days)
            effective_weeks = max(int((diff_days / 7) + 0.999), 4)
    except Exception as e:
        logger.warning("export: effective_weeks calculation failed: %s", e)
        effective_weeks = 4

    try:
        current_sessions = [s for s in sessions if (s.get("block") or "current") == "current"]
        current_week = max(
            (int(s.get("week_number", 0)) for s in current_sessions if s.get("week_number")),
            default=effective_weeks,
        )
        bundle["weekly"] = _build_sectioned_week_analysis(
            program,
            current_sessions,
            glossary,
            week_start=max(1, current_week - effective_weeks + 1),
            week_end=current_week,
            ref_date=datetime.utcnow().date().isoformat(),
        )
    except Exception as e:
        logger.warning("export: weekly_analysis failed: %s", e)

    try:
        if (getattr(store, "export_access", None) or {}).get("is_self"):
            bundle["correlation"] = _read_cached_correlation(active_pk, weeks=effective_weeks)
    except Exception as e:
        logger.warning("export: correlation cache read failed: %s", e)


    access = getattr(store, 'export_access', None)
    if access:
        allowed = set(access['permissions'])
        for field, domain in {'weekly': 'analytics', 'correlation': 'analytics', 'program_evaluation': 'analytics', 'glossary': 'glossary', 'federation_library': 'federation', 'weight_log': 'weight-log', 'max_history': 'performance', 'lift_profiles': 'lift-profiles'}.items():
            if f'{domain}:read' not in allowed:
                bundle[field] = [] if field in ('weight_log', 'max_history', 'glossary', 'lift_profiles') else None
    return bundle


def export_program_markdown(args: Dict[str, Any]) -> dict:
    """Generate a markdown export of the current program and return its content as a string."""
    from .export import build_program_markdown

    store = _get_store(args)
    program = with_competition_entries(_run_async(store.get_program()), store.pk)
    from services.publication import program_view
    access = args.get('_access')
    if access:
        program = program_view(program, access)
    store.export_access = access
    sessions = program.get("sessions", []) if isinstance(program, dict) else []
    analysis = _build_analysis_bundle(program, sessions, store)
    scoped_program = _scope_program_to_current_block(program)
    with tempfile.TemporaryDirectory() as out_dir:
        out_path = os.path.join(out_dir, "program_history.md")
        build_program_markdown(scoped_program, out_path, analysis=analysis, export_context=analysis)
        with open(out_path, "r", encoding="utf-8") as exported:
            markdown = exported.read()
    return {"markdown": markdown, "length": len(markdown)}
