"""IF plan/route/deliver flow."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from channels.status import StatusType, send_status
from config import (
    IF_DEFAULT_DIRECT_MODEL,
    IF_DIRECT_LLM_TOOL_ROUNDS,
    IF_TECHNICAL_ARTIFACT_EXCLUDES,
    OPENCODE_PLANNER_MODEL,
)
from files import FileRef, strip_files_line
from mcp_runtime import get_mcp_manager

from .direct_llm import call_openrouter_chat
from .history import write_history
from .model_catalog import format_model_catalog, load_model_ids
from .opencode import run_opencode
from .plan import IFPlan, PlanParseError, fallback_plan, parse_plan_file
from .session_dirs import resolve_session_dir

if False:  # pragma: no cover
    from storage.models import WebhookRecord

logger = logging.getLogger(__name__)


@dataclass
class FlowResult:
    content: str
    file_refs: list[FileRef] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    plan: Optional[IFPlan] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _main_system_prompt() -> str:
    path = _project_root() / "app" / "main_system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return "You are IF, a direct, pragmatic assistant."


def _latest_user_prompt(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def _directive_block(types: list[str] | None = None) -> str:
    try:
        from storage.factory import get_directive_store

        store = get_directive_store()
        if types is None:
            directives = store.get_for_subagent(["core"])
        else:
            directives = store.get_for_subagent(types)
        return store.format_directives(directives)
    except Exception as exc:
        logger.debug("Directive injection unavailable: %s", exc)
        return ""


def _specialist_catalog() -> tuple[set[str], str]:
    try:
        from agent.specialists import list_specialists
    except Exception as exc:
        logger.warning("Specialist catalog unavailable: %s", exc)
        return {"general"}, "- general: General IF response"

    specialists = list_specialists()
    lines = []
    slugs = {"general"}
    for spec in specialists:
        slugs.add(spec.slug)
        lines.append(f"- {spec.slug}: {spec.description}")
    return slugs, "\n".join(lines)


def _get_specialist(slug: str):
    try:
        from agent.specialists import get_specialist

        return get_specialist(slug)
    except Exception:
        return None


def _specialist_prompt(specialist_slug: str, task: str) -> tuple[str, list[str]]:
    spec = _get_specialist(specialist_slug)
    if spec is None:
        return "", []

    directives = _directive_block(spec.directive_types)
    try:
        from agent.specialists import render_specialist_prompt

        prompt = render_specialist_prompt(
            specialist=spec,
            task=task,
            directives=directives,
        )
    except Exception as exc:
        logger.warning("Specialist prompt render failed for %s: %s", specialist_slug, exc)
        prompt = f"{spec.description}\n\nTask:\n{task}\n\nDirectives:\n{directives}"
    return prompt, list(spec.tools)


def _planner_prompt(history_path: Path, model_ids: list[str], specialist_catalog: str) -> str:
    return f"""You are IF's planning stage.

Read `{history_path.name}` in the current directory. Write `plan.md` in the same directory.

The file must contain YAML front matter with exactly these fields:
- intent_summary: short string
- interaction_type: one of social, domain, technical
- specialist: one of the listed specialist slugs, or general for social
- thinking_mode: boolean
- selected_model: one model ID from the eligible model list

After the front matter, write the full self-contained prompt to pass to the next stage.

IF personality and core posture:
{_main_system_prompt()}

Core directives:
{_directive_block(["core"])}

Specialists:
{specialist_catalog}

Eligible models:
{format_model_catalog(model_ids)}

Classification guide:
- social: ordinary conversation, emotional support, general answer, no domain tools.
- domain: needs a domain specialist or IF MCP tools, especially health, finance, diary, proposals, temporal, supplement research.
- technical: code, repository edits, shell work, generated files, debugging, build/test work.

Select the model yourself from the eligible list. Do not use router presets or @preset names.
"""


async def _run_planner(session_dir: Path, messages: list[dict[str, Any]]) -> IFPlan:
    model_ids = load_model_ids()
    selected_fallback = model_ids[0] if model_ids else IF_DEFAULT_DIRECT_MODEL
    known_specialists, catalog = _specialist_catalog()
    history_path = write_history(session_dir, messages)

    try:
        result = await run_opencode(
            agent="plan",
            model=OPENCODE_PLANNER_MODEL,
            session_dir=session_dir,
            prompt=_planner_prompt(history_path, model_ids, catalog),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        plan_path = session_dir / "plan.md"
        if not plan_path.exists():
            raise FileNotFoundError("opencode planner did not write plan.md")
        return parse_plan_file(plan_path, model_ids, known_specialists)
    except (Exception, PlanParseError) as exc:
        logger.warning("Planner failed; using fallback plan: %s", exc)
        prompt = _latest_user_prompt(messages)
        return fallback_plan(
            prompt=prompt,
            selected_model=selected_fallback,
            specialist="general",
            interaction_type="social",
            reason=f"Planner fallback: {type(exc).__name__}",
        )


def _messages_for_direct(system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


async def _run_social(plan: IFPlan, http_client: httpx.AsyncClient) -> str:
    system = "\n\n".join(
        part
        for part in (
            _main_system_prompt(),
            "Core directives:",
            _directive_block(["core"]),
        )
        if part
    )
    return await call_openrouter_chat(
        http_client=http_client,
        model=plan.selected_model,
        messages=_messages_for_direct(system, plan.prompt),
        max_tool_rounds=0,
    )


async def _run_domain(plan: IFPlan, http_client: httpx.AsyncClient) -> str:
    specialist_block, specialist_tools = _specialist_prompt(plan.specialist, plan.prompt)
    manager = get_mcp_manager()
    tools = manager.tools_for_names(set(specialist_tools) | {"get_current_date"})
    system = "\n\n".join(
        part
        for part in (
            _main_system_prompt(),
            "Core directives:",
            _directive_block(["core"]),
            f"Specialist directives for `{plan.specialist}`:",
            specialist_block,
        )
        if part
    )
    return await call_openrouter_chat(
        http_client=http_client,
        model=plan.selected_model,
        messages=_messages_for_direct(system, plan.prompt),
        tools=tools,
        tool_dispatcher=manager.call_tool,
        max_tool_rounds=IF_DIRECT_LLM_TOOL_ROUNDS,
    )


def _snapshot_files(session_dir: Path) -> set[Path]:
    if not session_dir.exists():
        return set()
    return {p.resolve() for p in session_dir.rglob("*") if p.is_file()}


def _artifact_refs(session_dir: Path, before: set[Path]) -> list[FileRef]:
    refs: list[FileRef] = []
    for path in sorted(p for p in session_dir.rglob("*") if p.is_file()):
        if path.name in IF_TECHNICAL_ARTIFACT_EXCLUDES:
            continue
        resolved = path.resolve()
        if resolved in before:
            continue
        rel = path.relative_to(session_dir)
        refs.append(FileRef(path=str(path), description=f"Generated artifact: {rel}"))
    return refs


async def _run_technical(plan: IFPlan, session_dir: Path) -> tuple[str, list[FileRef]]:
    before = _snapshot_files(session_dir)
    technical_prompt = f"""Use the current directory as the session workspace.

Implement the user's request from the prompt below. Write the final user-facing answer to `response.md`.
Keep any generated deliverable files in this session directory.

Prompt:
{plan.prompt}
"""
    await send_status(StatusType.SUBAGENT_SPAWNING, "Technical Build Started", plan.selected_model)
    result = await run_opencode(
        agent="build",
        model=plan.selected_model,
        session_dir=session_dir,
        prompt=technical_prompt,
    )
    if result.returncode != 0:
        await send_status(StatusType.SUBAGENT_FAILED, "Technical Build Failed", result.stderr[:500])
        raise RuntimeError(result.stderr or result.stdout)
    await send_status(StatusType.SUBAGENT_COMPLETED, "Technical Build Completed", plan.selected_model)

    review_prompt = """Review the build output in this directory.

Write `review.md`.
If the build must be retried, write `RETRY` on line 1 and then explain the required changes.
Otherwise write `OK` on line 1 and a concise review summary after it.
"""
    review = await run_opencode(
        agent="plan",
        model=OPENCODE_PLANNER_MODEL,
        session_dir=session_dir,
        prompt=review_prompt,
    )
    if review.returncode != 0:
        logger.warning("Technical review failed: %s", review.stderr[:1000])

    review_path = session_dir / "review.md"
    if review_path.exists():
        first_line = review_path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        if first_line and first_line[0].strip() == "RETRY":
            retry_prompt = f"""{technical_prompt}

Reviewer requested one retry. Review context:
{review_path.read_text(encoding="utf-8", errors="replace")}
"""
            retry = await run_opencode(
                agent="build",
                model=plan.selected_model,
                session_dir=session_dir,
                prompt=retry_prompt,
            )
            if retry.returncode != 0:
                raise RuntimeError(retry.stderr or retry.stdout)

    response_path = session_dir / "response.md"
    if response_path.exists():
        content = response_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        content = (result.stdout or "").strip() or "Technical task completed, but response.md was not written."

    return content, _artifact_refs(session_dir, before)


async def run_if_flow(
    *,
    request_data: dict[str, Any],
    http_client: httpx.AsyncClient,
    cache_key: str,
    context_id: str,
    webhook: Optional["WebhookRecord"] = None,
) -> FlowResult:
    del context_id  # reserved for future memory/directive context refinement
    messages = request_data.get("messages") or []
    session_dir = resolve_session_dir(request_data, webhook, cache_key)
    plan = await _run_planner(session_dir, messages)

    await send_status(
        StatusType.MODEL_SELECTED,
        "Route Selected",
        f"{plan.interaction_type} / {plan.specialist} / {plan.selected_model}",
    )

    if plan.interaction_type == "technical":
        content, refs = await _run_technical(plan, session_dir)
    elif plan.interaction_type == "domain":
        content = await _run_domain(plan, http_client)
        refs = []
    else:
        content = await _run_social(plan, http_client)
        refs = []

    cleaned, inline_refs = strip_files_line(content)
    refs.extend(inline_refs)
    return FlowResult(content=cleaned, file_refs=refs, plan=plan)


async def run_specialist_flow(
    *,
    specialist_slug: str,
    task: str,
    http_client: httpx.AsyncClient,
    selected_model: str | None = None,
) -> str:
    model_ids = load_model_ids()
    model = selected_model or (model_ids[0] if model_ids else IF_DEFAULT_DIRECT_MODEL)
    plan = fallback_plan(
        prompt=task,
        selected_model=model,
        specialist=specialist_slug,
        interaction_type="domain",
        reason=f"Direct specialist command: {specialist_slug}",
    )
    return await _run_domain(plan, http_client)


def materialize_file_ref(ref: FileRef, cache_key: str) -> dict[str, Any] | None:
    path = Path(ref.path)
    if not path.exists() or not path.is_file():
        return None

    # Keep a temp copy for Discord upload compatibility.
    import tempfile

    temp_dir = Path(tempfile.gettempdir()) / "if-attachments" / cache_key
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / path.name
    try:
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
    except Exception:
        return None

    return {
        "filename": path.name,
        "url": f"/files/sandbox/{cache_key}/{path.name}",
        "local_path": str(target),
        "content_type": "application/octet-stream",
        "description": ref.description,
    }

