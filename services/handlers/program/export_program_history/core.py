"""Lambda core for export_program_history — replicates tools/health/tool.py dispatcher.

Exports the full training program to an Excel (.xlsx) or Markdown (.md) file.
AI section calls (program_evaluation) are intentionally omitted from the
analysis bundle; correlation uses cached DynamoDB values only.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from importlib import import_module
from services.lib.block_scope import ACTIVE, current_block_id, in_block, resolve_block_id, scope_entries, scope_program
import os
import re
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from services.lib.aws import dynamodb_resource

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store(args):
    """Lazily create and return the ProgramStore singleton."""
    import os
    from services.lib.program_store import ProgramStore as _PS
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
    dynamodb = dynamodb_resource("dynamodb", region_name="ca-central-1")
    table = dynamodb.Table(table_name)
    resp = table.get_item(Key={"pk": pk, "sk": "glossary#v1"})
    item = resp.get("Item")
    if not item:
        return []
    return _sanitize_decimals(item.get("exercises", []))


def _get_versioned_item_sync(table_name: str, pk: str, sk: str) -> dict | None:
    dynamodb = dynamodb_resource("dynamodb", region_name="ca-central-1")
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


def _session_in_window(session: dict, window: dict) -> bool:
    week_start, week_end = window.get("week_start"), window.get("week_end")
    if week_start is not None and week_end is not None:
        week = int(session.get("week_number") or 0)
        return int(week_start) <= week <= int(week_end)
    date = str(session.get("date") or "")[:10]
    if window.get("window_start") and date < window["window_start"]:
        return False
    if window.get("window_end") and date > window["window_end"]:
        return False
    return True


def _scope_export_program(program: dict, block: str | None, window: dict) -> tuple[dict, str]:
    target = resolve_block_id(program, block)
    scoped = scope_program(program, target)
    scoped["sessions"] = [s for s in scoped.get("sessions", []) if _session_in_window(s, window)]
    entry_window = dict(window)
    if not entry_window.get("window_start") and not entry_window.get("window_end"):
        blocks = sorted((program.get("meta") or {}).get("blocks") or [], key=lambda item: str(item.get("start_date") or ""))
        target_index = next((index for index, item in enumerate(blocks) if str(item.get("id") or item.get("block_id") or "") == target), None)
        if target_index is not None:
            entry_window["window_start"] = str(blocks[target_index].get("start_date") or "")[:10]
            next_start = str(blocks[target_index + 1].get("start_date") or "")[:10] if target_index + 1 < len(blocks) else ""
            if next_start:
                from datetime import date
                entry_window["window_end"] = (date.fromisoformat(next_start) - timedelta(days=1)).isoformat()
    if isinstance(scoped.get("diet_notes"), list):
        scoped["diet_notes"] = _entries_in_window(scoped["diet_notes"], scoped, entry_window)
    session_block = ACTIVE if target == current_block_id(program) else target
    return scoped, session_block


def _block_date_range(program: dict, block: str | None) -> tuple[str | None, str | None]:
    target = resolve_block_id(program, block)
    active = current_block_id(program)
    session_dates = [(str(s.get("date"))[:10], in_block(s, target, active)) for s in program.get("sessions", []) if s.get("date")]
    block_dates = sorted(date for date, inside in session_dates if inside)
    if not block_dates:
        return None, None
    if target == active:
        return block_dates[0], None
    following = sorted(date for date, inside in session_dates if not inside and date > block_dates[-1])
    return block_dates[0], following[0] if following else None


def _export_window(args: dict) -> dict:
    window = {key: args.get(key) for key in ("window_key", "window_start", "window_end", "week_start", "week_end")}
    window = {key: value for key, value in window.items() if value not in (None, "")}
    for key in ("week_start", "week_end"):
        if key in window:
            window[key] = int(window[key])
    return window


def _read_cached_correlation(pk: str, weeks: int = 4) -> dict | None:
    """Return the cached correlation report for the current window, or None."""
    import boto3
    from .config import IF_HEALTH_TABLE_NAME

    today = datetime.utcnow().date()
    raw_cutoff = today - timedelta(weeks=weeks)
    window_start = (raw_cutoff - timedelta(days=raw_cutoff.weekday())).isoformat()
    cache_sk = f"corr_report#{window_start}_{weeks}w"

    table = dynamodb_resource("dynamodb", region_name="ca-central-1").Table(IF_HEALTH_TABLE_NAME)
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


def _build_analysis_bundle(program: dict, sessions: list[dict], store, *, session_block: str = ACTIVE, window: dict | None = None) -> dict:
    """Assemble the analysis bundle threaded into the XLSX export.

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
            max_history_item = _run_async(import_module("services.handlers.maxes.max_history_get.core").max_history_get({"pk": active_pk, "version": version_token, "_access": getattr(store, "export_access", None) or {}}))
            bundle["max_history"] = (max_history_item or {}).get("entries", [])
        else:
            bundle["max_history"] = []
    except Exception as e:
        logger.warning("export: max history fetch failed (%s); continuing without it", e)
        bundle["max_history"] = []

    dated_sessions = sorted((s for s in sessions if s.get("date")), key=lambda x: x["date"])
    if dated_sessions:
        first = datetime.fromisoformat(dated_sessions[0]["date"][:10])
        last = datetime.fromisoformat(dated_sessions[-1]["date"][:10])
        effective_weeks = max(int((abs((last - first).days) / 7) + 0.999), 1)
    else:
        effective_weeks = 1

    try:
        if window:
            cached = None
            window_key = window.get("window_key")
            if window_key:
                from services.lib.analysis_cache import AnalysisCacheStore
                cached = AnalysisCacheStore(pk=active_pk).get_window_analysis(str(window_key), None if session_block == ACTIVE else session_block)
            bundle["weekly"] = cached.get("data") if cached else _build_sectioned_analysis(
                program,
                sessions,
                glossary,
                weeks=effective_weeks,
                block=session_block,
                window_start=window.get("window_start"),
                window_end=window.get("window_end"),
                week_start=window.get("week_start"),
                week_end=window.get("week_end"),
                ref_date=window.get("window_end") or datetime.utcnow().date().isoformat(),
            )
        else:
            weeks = [int(s["week_number"]) for s in sessions if s.get("week_number")]
            bundle["weekly"] = _build_sectioned_analysis(
                program,
                sessions,
                glossary,
                weeks=effective_weeks,
                block=session_block,
                week_start=min(weeks, default=1),
                week_end=max(weeks, default=1),
                ref_date=(dated_sessions[-1]["date"][:10] if dated_sessions else datetime.utcnow().date().isoformat()),
            )
    except Exception as e:
        logger.warning("export: weekly_analysis failed: %s", e)

    try:
        if session_block == ACTIVE and (getattr(store, "export_access", None) or {}).get("is_self"):
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


def _normalize_export_format(format_value: str | None) -> str:
    export_format = str(format_value or "xlsx").strip().lower()
    if export_format in ("md", "markdown"):
        return "markdown"
    if export_format == "xlsx":
        return "xlsx"
    raise ValueError(f"Unsupported export format: {format_value!r}. Use 'xlsx' or 'markdown'.")


def _export_filename(program: dict, session_block: str, window: dict, extension: str) -> str:
    block_label = "current" if session_block == ACTIVE else session_block
    if window.get("week_start") is not None and window.get("week_end") is not None:
        span = f"_W{window['week_start']}-W{window['week_end']}"
    elif window.get("window_start") or window.get("window_end"):
        span = f"_{window.get('window_start', '')}_{window.get('window_end', '')}"
    else:
        span = ""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", f"program_{block_label}{span}.{extension}")


def _write_program_export(program: dict, session_block: str, window: dict, store, out_dir: str, format_value: str | None) -> tuple[str, str, str]:
    from .export import build_program_markdown, build_program_xlsx

    export_format = _normalize_export_format(format_value)
    analysis = _build_analysis_bundle(program, program.get("sessions", []), store, session_block=session_block, window=window)
    active = current_block_id(program)
    target = active if session_block == ACTIVE else session_block
    if isinstance(analysis.get("weight_log"), list):
        analysis["weight_log"] = _entries_in_window(scope_entries(analysis["weight_log"], target, program, "weight_log"), program, window)
    if isinstance(analysis.get("max_history"), list):
        analysis["max_history"] = _entries_in_window(analysis["max_history"], program, window)

    if export_format == "markdown":
        filename = _export_filename(program, session_block, window, "md")
        build_program_markdown(program, os.path.join(out_dir, filename), analysis=analysis, export_context=analysis)
        return filename, "Markdown export of training history", export_format

    filename = _export_filename(program, session_block, window, "xlsx")
    build_program_xlsx(program, os.path.join(out_dir, filename), analysis=analysis, export_context=analysis)
    return filename, "Excel export of training history", export_format


def _entries_in_window(entries: list[dict], program: dict, window: dict | None = None) -> list[dict]:
    window = window or {}
    dates = sorted(str(s.get("date") or "")[:10] for s in program.get("sessions", []) if s.get("date"))
    start = window.get("window_start") or (dates[0] if dates else None)
    end = window.get("window_end") or (dates[-1] if dates else None)
    if not start or not end:
        return []
    return [e for e in entries if start <= str(e.get("date") or "")[:10] <= end]


def export_program_history(args: dict) -> dict:
    from services.handlers.program.program_get.core import program_get
    store = _get_store(args)
    program = _run_async(program_get({
        "pk": args["pk"],
        "block": args.get("block") or ACTIVE,
        "window_start": args.get("window_start"),
        "window_end": args.get("window_end"),
        "_access": args.get("_access"),
        "_store": store,
    }))
    from services.publication import program_view
    access = args.get('_access')
    if access:
        program = program_view(program, access)
    store.export_access = access
    window = _export_window(args)
    scoped, session_block = _scope_export_program(program, args.get("block"), window)
    with tempfile.TemporaryDirectory() as out_dir:
        filename, _description, export_format = _write_program_export(scoped, session_block, window, store, out_dir, args.get("format"))
        with open(os.path.join(out_dir, filename), "rb") as exported:
            content_base64 = base64.b64encode(exported.read()).decode()
    return {"filename": filename, "format": export_format, "content_base64": content_base64}
