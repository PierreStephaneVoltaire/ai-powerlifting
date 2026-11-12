from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict

from services.runtime import analytics_client
from services.runtime.dispatch import OperationError
from services.runtime import valkey
from services.runtime.block_scope import scope_program


def _get_store():
    from services.runtime.program_store import ProgramStore
    return ProgramStore(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


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


def _build_sectioned_week_analysis(
    program: dict,
    sessions: list[dict],
    *,
    week_start: int,
    week_end: int,
    ref_date: str,
) -> dict:
    return analytics_client.weekly_analysis(
        program,
        sessions,
        weeks=max(1, week_end - week_start + 1),
        block="current",
        week_start=week_start,
        week_end=week_end,
        ref_date=ref_date,
    )


def _is_self(args: Dict[str, Any]) -> bool:
    access = args.get("_access")
    return not isinstance(access, dict) or bool(access.get("is_self"))


def _markdown_source_requirements(args: Dict[str, Any]) -> dict:
    from services.runtime.source_access import read_requirements
    requirements = read_requirements(args.get("_access") or {})
    requirements["permissions"] = [
        permission for permission in requirements.get("permissions", [])
        if permission != "analytics:read"
    ]
    competition_ids = requirements.get("competition_ids")
    if isinstance(competition_ids, list):
        requirements["competition_ids"] = sorted(competition_ids)
    return requirements


def _markdown_cache_key(args: Dict[str, Any]) -> str:
    if _is_self(args):
        return "self"
    requirements = _markdown_source_requirements(args)
    return "scope#" + hashlib.sha256(json.dumps(requirements, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _visible_program(program: dict, args: Dict[str, Any]) -> dict:
    access = args.get("_access")
    if not isinstance(access, dict) or access.get("is_self"):
        return program
    from services.runtime.publication import program_view
    visible = program_view(program, access)
    permissions = set(access.get("permissions", []))
    from services.runtime.access import META_DOMAINS
    allowed_meta = {"program_name", "blocks"}
    for domain, fields in META_DOMAINS.items():
        if f"{domain}:read" in permissions:
            allowed_meta.update(fields)
    if "profile:read" in permissions:
        allowed_meta.add("sex")
    if "program:read" in permissions:
        allowed_meta.update({"program_start", "version_label", "training_notes", "change_log", "block_notes"})
    visible["meta"] = {key: value for key, value in (visible.get("meta") or {}).items() if key in allowed_meta}
    settings = visible.get("settings")
    if isinstance(settings, dict):
        visible["settings"] = {"sex": settings["sex"]} if "profile:read" in permissions and "sex" in settings else {}
    return visible


def _markdown_export_sex(program: dict, args: Dict[str, Any]) -> str:
    access = args.get("_access")
    if isinstance(access, dict) and not access.get("is_self") and "profile:read" not in access.get("permissions", []):
        return "undisclosed"
    return str((program.get("meta") or {}).get("sex") or (program.get("settings") or {}).get("sex") or "male").lower()


def _load_program(store, args: Dict[str, Any]) -> dict:
    from services.runtime.competition_entries import with_competition_entries
    store.invalidate_cache()
    program = _run_async(store.get_program())
    return _visible_program(with_competition_entries(program, store.pk), args)


def _markdown_record_key(pk: str, args: Dict[str, Any], today: str) -> str:
    from services.runtime.analysis_version import current
    return f"pl:markdown:{pk}:{_markdown_cache_key(args)}:{today}:{current(pk)}"


def _render_markdown(pk: str, program: dict, today: str, args: Dict[str, Any]) -> str:
    from .export import build_program_markdown
    sessions = scope_program(program).get("sessions", [])
    current_week = max((int(s.get("week_number", 0)) for s in sessions if s.get("week_number")), default=1)
    try:
        analysis = _build_sectioned_week_analysis(program, sessions, week_start=1, week_end=current_week, ref_date=today)
    except OperationError:
        analysis = None
    bundle = {"weekly": analysis, "pk": pk, "sex": _markdown_export_sex(program, args)}
    with tempfile.TemporaryDirectory() as directory:
        out_path = os.path.join(directory, "program.md")
        build_program_markdown(scope_program(program), out_path, analysis=bundle, export_context=bundle)
        with open(out_path, "r", encoding="utf-8") as f:
            return f.read()


def get_analysis_markdown(args: Dict[str, Any]) -> Dict[str, Any]:
    from services.runtime.source_access import authorize_source

    store = _get_store()
    pk = store.pk
    today = datetime.now(timezone.utc).date().isoformat()
    key = _markdown_record_key(pk, args, today)
    force_refresh = bool(args.get("refresh"))

    cached = None if force_refresh else valkey.get_json(key)
    if cached:
        if not _is_self(args):
            authorize_source(cached.get("access_requirements"), args.get("_access") or {})
        return {"markdown": cached["markdown"], "generated_at": cached["generated_at"], "cached": True}
    if args.get("cache_only"):
        return {"cached": False, "cache_miss": True}

    program = _load_program(store, args)
    markdown = _render_markdown(pk, program, today, args)
    record = {"markdown": markdown, "generated_at": datetime.now(timezone.utc).isoformat()}
    if not _is_self(args):
        record["access_requirements"] = _markdown_source_requirements(args)
    valkey.set_json(key, record)
    return {"markdown": markdown, "generated_at": record["generated_at"], "cached": False}
