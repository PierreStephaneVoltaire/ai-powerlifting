"""Async template import endpoints for powerlifting spreadsheet uploads."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from config import OPENCODE_WORKSPACE_BASE, PROJECT_ROOT
from flow.runner import run_specialist_flow
from flow.session_dirs import safe_segment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/health/template-imports", tags=["template_imports"])

ALLOWED_SUFFIXES = {".xlsx", ".xls", ".csv"}
IMPORT_OPENCODE_TIMEOUT_SECONDS = int(os.getenv("TEMPLATE_IMPORT_OPENCODE_TIMEOUT_SECONDS", "300"))


def _health_tools_path() -> Path:
    return PROJECT_ROOT / "tools" / "health"


def _get_template_store():
    tools_path = str(_health_tools_path())
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    from template_store import TemplateStore

    return TemplateStore(
        table_name=os.environ.get("IF_TEMPLATES_TABLE_NAME", "if-health-templates"),
        pk=os.environ.get("IF_TEMPLATES_LIBRARY_PK", "template_library"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def _public_job(item: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "job_id",
        "status",
        "filename",
        "template_sk",
        "warnings",
        "error",
        "created_at",
        "updated_at",
        "author",
        "author_pk",
    }
    return {key: item.get(key) for key in allowed if key in item}


def _job_workspace(job_id: str) -> Path:
    path = Path(OPENCODE_WORKSPACE_BASE) / "template-imports" / safe_segment(job_id, "job")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(filename: str) -> str:
    return safe_segment(Path(filename or "template.xlsx").name, "template.xlsx")


async def _mark_job(job_id: str, updates: dict[str, Any]) -> None:
    store = _get_template_store()
    await store.update_import_job(job_id, updates)


async def _find_created_template(job_id: str, actor_pk: str) -> str | None:
    store = _get_template_store()
    templates = await store.list_templates(include_archived=True, actor_pk=actor_pk)
    for template in templates:
        if template.get("import_job_id") == job_id:
            return str(template.get("sk"))
    return None


def _looks_like_template_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("meta"), dict)
        and isinstance(payload.get("sessions"), list)
    )


def _generated_payload_candidates(session_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in session_dir.glob("*.json"):
        lowered = path.name.lower()
        if "payload" in lowered or "template" in lowered:
            candidates.append(path)
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


async def _create_from_generated_payload(
    session_dir: Path,
    *,
    job_id: str,
    filename: str,
    actor_pk: str,
    author: str,
) -> str | None:
    tools_path = str(_health_tools_path())
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    from core import template_create_from_payload

    for path in _generated_payload_candidates(session_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not _looks_like_template_payload(payload):
            continue
        meta = payload.setdefault("meta", {})
        meta.setdefault("source_filename", filename)
        result = await template_create_from_payload(
            payload,
            actor_pk=actor_pk,
            author=author,
            published=False,
            import_job_id=job_id,
        )
        sk = result.get("sk")
        if sk:
            logger.info("Template import job %s saved generated payload from %s", job_id, path.name)
            return str(sk)
    return None


def _template_import_prompt(job_id: str, filename: str, actor_pk: str, author: str) -> str:
    payload_hint = {
        "actor_pk": actor_pk,
        "author": author,
        "published": False,
        "import_job_id": job_id,
    }
    return f"""Create a reusable powerlifting training template draft from the uploaded spreadsheet.

Spreadsheet path in this workspace: uploads/{filename}
Template import job id: {job_id}

Hard requirements:
- Treat this as a reusable template, not a dated session import.
- Inspect workbook sheets, formulas, nearby labels, and cell values with Python libraries such as openpyxl, csv, and pandas.
- LiftVault-style spreadsheets are often matrix layouts, not clean header rows. Do not rely only on the first row as headers.
- Create relative template weeks and days. Do not create dated sessions.
- Normalize percentage loads as load_type="percentage" with decimal load_value, e.g. 75% -> 0.75.
- Normalize RPE prescriptions as load_type="rpe" with rpe_target.
- If formula-derived loads clearly reference max/input cells, convert them back to percentage prescriptions when possible.
- If data is ambiguous, include warnings in the template description or notes rather than inventing certainty.
- Before calling the template tool, write the complete payload JSON to `template_payload.json`.
- Save one unpublished draft by calling template_create_from_payload with this metadata:
{json.dumps(payload_hint, indent=2)}

Expected template payload shape:
{{
  "meta": {{
    "name": "program/template name",
    "description": "short parse summary and warnings",
    "source_filename": "{filename}",
    "estimated_weeks": 0,
    "days_per_week": 0,
    "archived": false
  }},
  "phases": [
    {{"name": "string", "week_start": 1, "week_end": 4, "intent": "string"}}
  ],
  "sessions": [
    {{
      "week_number": 1,
      "day_index": 1,
      "day_of_week": "Monday",
      "label": "W1D1",
      "exercises": [
        {{
          "name": "Squat",
          "glossary_id": "squat",
          "sets": 3,
          "reps": 5,
          "load_type": "percentage",
          "load_value": 0.75,
          "rpe_target": null,
          "notes": ""
        }}
      ]
    }}
  ]
}}

After the tool call, write response.md with the created template SK and a concise warning summary.
"""


async def _run_import_job(job_id: str, filename: str, actor_pk: str, author: str) -> None:
    await _mark_job(job_id, {"status": "running"})
    session_dir = _job_workspace(job_id)
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            content, _refs = await run_specialist_flow(
                specialist_slug="powerlifting_coach",
                task=_template_import_prompt(job_id, filename, actor_pk, author),
                http_client=http_client,
                session_dir=session_dir,
                context_id=actor_pk,
                cache_key=f"template-import-{job_id}",
                opencode_timeout=IMPORT_OPENCODE_TIMEOUT_SECONDS,
            )
        template_sk = await _find_created_template(job_id, actor_pk)
        if not template_sk:
            template_sk = await _create_from_generated_payload(
                session_dir,
                job_id=job_id,
                filename=filename,
                actor_pk=actor_pk,
                author=author,
            )
        if not template_sk:
            snippet = (content or "").strip().replace("\n", " ")[:800]
            raise RuntimeError(f"OpenCode completed without creating a template for job {job_id}. {snippet}")
        await _mark_job(job_id, {
            "status": "succeeded",
            "template_sk": template_sk,
        })
    except Exception as exc:
        template_sk = await _create_from_generated_payload(
            session_dir,
            job_id=job_id,
            filename=filename,
            actor_pk=actor_pk,
            author=author,
        )
        if template_sk:
            await _mark_job(job_id, {
                "status": "succeeded",
                "template_sk": template_sk,
                "warnings": [
                    "OpenCode timed out or exited before reporting completion; saved the generated template payload it wrote in the job workspace.",
                ],
            })
            return
        logger.exception("Template import job failed: %s", job_id)
        await _mark_job(job_id, {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        })


@router.post("")
async def create_template_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    author_pk: str = Form(...),
    author: str = Form(""),
) -> dict[str, Any]:
    filename = _safe_filename(file.filename or "template.xlsx")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .xlsx, .xls, and .csv uploads are supported")
    if not author_pk.strip():
        raise HTTPException(status_code=400, detail="author_pk is required")

    job_id = str(uuid.uuid4())
    session_dir = _job_workspace(job_id)
    uploads_dir = session_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    target = uploads_dir / filename
    target.write_bytes(await file.read())

    now_ttl = int(time.time()) + 30 * 86400
    store = _get_template_store()
    await store.create_import_job({
        "job_id": job_id,
        "status": "queued",
        "filename": filename,
        "workspace": str(session_dir),
        "author_pk": author_pk,
        "author": author or author_pk,
        "ttl": now_ttl,
    })
    background_tasks.add_task(_run_import_job, job_id, filename, author_pk, author or author_pk)
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}")
async def get_template_import(job_id: str, actor_pk: str) -> dict[str, Any]:
    store = _get_template_store()
    item = await store.get_import_job(job_id, actor_pk=actor_pk)
    if not item:
        raise HTTPException(status_code=404, detail="Template import job not found")
    return _public_job(item)
