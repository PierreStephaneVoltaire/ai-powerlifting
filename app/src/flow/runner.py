"""IF plan/route/deliver flow."""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from channels.status import StatusType, send_status
from config import (
    IF_DEFAULT_DIRECT_MODEL,
    IF_TECHNICAL_ARTIFACT_EXCLUDES,
    OPENCODE_PLANNER_MODEL,
    PROJECT_ROOT,
    APP_SRC,
)
from files import FileRef, strip_files_line
from mcp_runtime import get_mcp_manager

from .direct_llm import call_openrouter_chat
from .history import write_history
from .model_catalog import format_model_catalog, load_model_ids, load_model_selection_rules
from .opencode import run_opencode
from .opencode_config import write_opencode_config
from .plan import IFPlan, PlanParseError, fallback_plan, parse_plan_file
from .session_dirs import resolve_session_dir
from .context import build_runtime_context, uploaded_file_paths

if False:  # pragma: no cover
    from storage.models import WebhookRecord

logger = logging.getLogger(__name__)


@dataclass
class FlowResult:
    content: str
    file_refs: list[FileRef] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    plan: Optional[IFPlan] = None


class PlannerFailure(RuntimeError):
    """Raised when the planner cannot produce a trustworthy route."""

    def __init__(self, exc: BaseException):
        self.detail = _exception_detail(exc)
        super().__init__(self.detail)


def _exception_detail(exc: BaseException) -> str:
    message = str(exc).strip() or repr(exc)
    return f"{type(exc).__name__}: {message}"


def _planner_failure_response(failure: PlannerFailure) -> str:
    detail = failure.detail
    if len(detail) > 900:
        detail = f"{detail[:897]}..."
    return (
        "I couldn't route this request because the planner failed, so I stopped instead "
        "of guessing an answer that might skip the right tools.\n\n"
        f"Planner error: `{detail}`"
    )


def _project_root() -> Path:
    return PROJECT_ROOT


def _main_system_prompt() -> str:
    path = PROJECT_ROOT / "main_system_prompt.txt"
    if not path.exists():
        path = PROJECT_ROOT / "app" / "main_system_prompt.txt"
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


def _specialist_prompt(specialist_slug: str, task: str) -> tuple[str, list[str], list[str]]:
    spec = _get_specialist(specialist_slug)
    if spec is None:
        return "", [], []

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
    return prompt, list(spec.tools), list(spec.mcp_servers)


def _planner_prompt(
    history_path: Path,
    model_ids: list[str],
    model_selection_rules: str,
    specialist_catalog: str,
    runtime_context: str,
    *,
    thinking_mode_requested: bool = False,
) -> str:
    thinking_hint = (
        "\nPondering mode is active for this conversation. Set thinking_mode: true unless the"
        " latest user message is purely administrative.\n"
        if thinking_mode_requested
        else ""
    )
    return f"""You are IF's planning stage.

Read `{history_path.name}` in the current directory. Write `plan.md` in the same directory.
`history.md` is incremental and edit-aware: Discord message edits update existing entries instead of creating a second message.
This directory is a persistent mounted conversation workspace. Previous files may still be present after a restart; use the newest `history.md` as the source of truth.

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
{thinking_hint}

Runtime compatibility and available context:
{runtime_context}

Specialists:
{specialist_catalog}

Eligible models:
{format_model_catalog(model_ids)}

Model selection policy from `models/model_selection_rules.md`:
{model_selection_rules or "No model selection rules file was found. Use the eligible model list and the request complexity to choose the smallest model that can answer well."}

Model selection requirements:
- `selected_model` must be exactly one ID from the eligible model list.
- Treat `model_ids.txt` as the hard allowlist and the model selection policy as preference guidance.
- If a policy rule references a model that is not in the eligible list, ignore that model and choose the closest eligible fit.
- Consider interaction type, specialist, task risk, current conversation flow, attached files, runtime context, and `history.md` size.
- Prefer cheaper models for small, simple, low-risk tasks. Prefer quality for powerlifting, technical, architectural, security, debugging, and multi-step tool work.
- Do not default to the cheapest or most expensive model. Move up when the task becomes harder, failures repeat, history grows, or long-context capacity matters; move down only when the latest turn is clearly simple and low-risk.

Classification guide:
- social: ordinary conversation, emotional support, general answer, no domain tools.
- domain: needs a domain specialist or IF MCP tools, especially health, finance, diary, proposals, temporal, supplement research.
- technical: code, repository edits, shell work, generated files, debugging, build/test work.
- media/file: domain with specialist `media_reader` unless it is clearly a spreadsheet import or code/data task.
- memory: if the operator asks IF to remember, update, supersede, or use stored facts, choose domain. Use specialist `general` unless another domain specialist is required.
- health routing: choose `powerlifting_coach` for health/training reads, coaching, and explicit health mutations such as "log", "update", "apply", "save", "record", or confirmed imports.
- finance read-write split: choose finance read specialists for analysis/advice. Choose write specialists only for explicit mutations such as "log", "update", "apply", "save", or "record". Read specialists may emit HANDOFF_REQUIRED blocks for writes.
- thinking_mode: if the operator asks for deep, adversarial, sequential, or multi-perspective reasoning, set true and choose the specialist/skill shape that best fits. The next stage can use the injected thinking skills and handoff blocks.

Select the model yourself from the eligible list. Do not use preset aliases or @preset names.
"""


async def _run_planner(
    session_dir: Path,
    messages: list[dict[str, Any]],
    *,
    history_events: list[dict[str, Any]] | None = None,
    runtime_context: str = "",
    uploaded_files: list[dict[str, Any]] | None = None,
    thinking_mode_requested: bool = False,
) -> IFPlan:
    model_ids = load_model_ids()
    model_selection_rules = load_model_selection_rules()
    known_specialists, catalog = _specialist_catalog()
    history_path = write_history(session_dir, messages, history_events=history_events)
    plan_path = session_dir / "plan.md"
    plan_path.unlink(missing_ok=True)
    write_opencode_config(session_dir, tool_names=[], mcp_servers=[])

    try:
        result = await run_opencode(
            agent="planner",
            model=OPENCODE_PLANNER_MODEL,
            session_dir=session_dir,
            prompt=_planner_prompt(
                history_path,
                model_ids,
                model_selection_rules,
                catalog,
                runtime_context,
                thinking_mode_requested=thinking_mode_requested,
            ),
            files=uploaded_file_paths(uploaded_files),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        if not plan_path.exists():
            output = (result.stderr or result.stdout).strip()
            if output:
                logger.warning("opencode planner returned without plan.md; output: %s", output[:2000])
            raise FileNotFoundError("opencode planner did not write plan.md")
        return parse_plan_file(plan_path, model_ids, known_specialists)
    except (Exception, PlanParseError) as exc:
        logger.warning("Planner failed; refusing fallback response: %s", exc)
        raise PlannerFailure(exc) from exc


def _messages_for_direct(system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


async def _run_social(plan: IFPlan, http_client: httpx.AsyncClient, runtime_context: str) -> str:
    system = "\n\n".join(
        part
        for part in (
            _main_system_prompt(),
            "Core directives:",
            _directive_block(["core"]),
            runtime_context,
        )
        if part
    )
    return await call_openrouter_chat(
        http_client=http_client,
        model=plan.selected_model,
        messages=_messages_for_direct(system, plan.prompt),
        max_tool_rounds=0,
    )


def _status_file(session_dir: Path) -> Path:
    status_dir = session_dir / ".if"
    status_dir.mkdir(parents=True, exist_ok=True)
    path = status_dir / "status.log"
    path.write_text("", encoding="utf-8")
    return path


async def _opencode_status(line: str) -> None:
    await send_status(StatusType.TOOL_STARTED, "opencode", line)


def _tool_protocol_block(tool_names: list[str]) -> str:
    pythonpath = os.pathsep.join([str(APP_SRC), str(PROJECT_ROOT)])
    invoke = f"PYTHONPATH={pythonpath!r} {sys.executable} -m mcp_runtime.invoke_tool"
    manager = get_mcp_manager()
    schemas = manager.tools_for_names(set(tool_names) | {"get_current_date"})
    lines = [
        "MCP tool protocol:",
        "- Native MCP tools are attached to this OpenCode run when available.",
        "- IF local MCP servers are filtered so they only list this specialist's declared tools.",
        "- Native OpenCode MCP tool names are server-prefixed, e.g. `if_health_health_get_session`.",
        "- If native MCP tools are unavailable, use this shell bridge fallback:",
        f"  `{invoke} <tool_name> '<json_args>'`",
        "- Example:",
        f"  `{invoke} get_current_date '{{}}'`",
        "- Call only the tools exposed in this run or listed below. Keep generated files in this session directory.",
        "- Before long operations and after tool calls, append a concise progress line to `.if/status.log`.",
        "",
        "Available tool schemas for this specialist:",
    ]
    if not schemas:
        lines.append("- No specialist MCP tools declared; `get_current_date` remains available.")
        return "\n".join(lines)

    for schema in schemas:
        fn = schema.get("function", {})
        params = fn.get("parameters") or {}
        lines.append(f"- {fn.get('name')}: {fn.get('description') or ''}")
        lines.append(f"  parameters: {params}")
    return "\n".join(lines)


def _domain_prompt(plan: IFPlan, runtime_context: str) -> str:
    specialist_block, specialist_tools, _ = _specialist_prompt(plan.specialist, plan.prompt)
    return "\n\n".join(
        part
        for part in (
            "You are running as IF inside a persistent mounted conversation workspace.",
            "Read `history.md` for conversation context. It is incremental and edit-aware.",
            "Write the final user-facing answer to `response.md`.",
            "Keep any generated deliverable files in this session directory.",
            "Use the IF personality and current directives below; do not rely on hardcoded generated agent files for personality.",
            _main_system_prompt(),
            "Core directives:",
            _directive_block(["core"]),
            f"Specialist directives for `{plan.specialist}`:",
            specialist_block,
            "Runtime compatibility, Discord contract, memory/media rules, and thinking skills:",
            runtime_context,
            _tool_protocol_block(specialist_tools),
            "If this task needs another specialist, write one or more HANDOFF_REQUIRED blocks with target, task or intended_change, and context. IF will execute them in order.",
            "Task prompt:",
            plan.prompt,
        )
        if part
    )


def _parse_handoffs(content: str) -> tuple[str, list[dict[str, str]]]:
    if "HANDOFF_REQUIRED" not in content:
        return content, []
    parts = re.split(r"\n?HANDOFF_REQUIRED:?\s*\n", content)
    primary = parts[0]
    blocks = parts[1:]
    handoffs: list[dict[str, str]] = []
    for block in blocks:
        current: dict[str, str] = {}
        current_key: str | None = None
        for raw_line in block.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("target:"):
                current_key = "target"
                current[current_key] = stripped.split(":", 1)[1].strip().strip("\"'")
            elif stripped.startswith("task:"):
                current_key = "task"
                current[current_key] = stripped.split(":", 1)[1].strip().strip("\"'")
            elif stripped.startswith("intended_change:"):
                current_key = "intended_change"
                current[current_key] = stripped.split(":", 1)[1].strip().strip("\"'")
            elif stripped.startswith("context:"):
                current_key = "context"
                current[current_key] = stripped.split(":", 1)[1].strip().strip("\"'")
            elif current_key:
                current[current_key] = f"{current.get(current_key, '')}\n{stripped}".strip()
        if current.get("target") and (current.get("task") or current.get("intended_change")):
            if not current.get("task"):
                current["task"] = current["intended_change"]
            handoffs.append(current)
    return primary.strip(), handoffs


async def _synthesize_handoffs(
    plan: IFPlan,
    session_dir: Path,
    runtime_context: str,
    primary: str,
    child_outputs: list[str],
    uploaded_files: list[dict[str, Any]] | None,
) -> str:
    if not child_outputs:
        return primary

    status_file = _status_file(session_dir)
    response_path = session_dir / "response.md"
    response_path.unlink(missing_ok=True)
    write_opencode_config(session_dir, tool_names=[], mcp_servers=[])
    agent = plan.specialist if (_project_root() / ".opencode" / "agent" / f"{plan.specialist}.md").exists() else "build"
    synthesis_prompt = "\n\n".join(
        [
            "You are IF integrating completed specialist handoffs.",
            "Read `history.md` only if needed for context.",
            "Write the final user-facing answer to `response.md`.",
            "Do not emit HANDOFF_REQUIRED unless a genuinely new blocking dependency remains.",
            "Preserve the IF personality, core directives, and domain caveats.",
            "Runtime context:",
            runtime_context,
            "Original specialist output before handoffs:",
            primary or "(none)",
            "Completed handoff outputs:",
            "\n\n---\n\n".join(child_outputs),
        ]
    )
    result = await run_opencode(
        agent=agent,
        model=plan.selected_model,
        session_dir=session_dir,
        prompt=synthesis_prompt,
        continue_session=True,
        status_file=status_file,
        status_callback=_opencode_status,
        files=uploaded_file_paths(uploaded_files),
    )
    if result.returncode != 0:
        logger.warning("Handoff synthesis failed for %s: %s", plan.specialist, result.stderr[:1000])
        return "\n\n".join(part for part in [primary, *child_outputs] if part).strip()

    if response_path.exists():
        return response_path.read_text(encoding="utf-8", errors="replace").strip()
    return (result.stdout or "").strip() or "\n\n".join(part for part in [primary, *child_outputs] if part).strip()


async def _run_domain(
    plan: IFPlan,
    session_dir: Path,
    runtime_context: str,
    uploaded_files: list[dict[str, Any]] | None = None,
    handoff_depth: int = 0,
) -> tuple[str, list[FileRef]]:
    before = _snapshot_files(session_dir)
    status_file = _status_file(session_dir)
    response_path = session_dir / "response.md"
    response_path.unlink(missing_ok=True)
    _, specialist_tools, specialist_mcp_servers = _specialist_prompt(plan.specialist, plan.prompt)
    write_opencode_config(session_dir, tool_names=specialist_tools, mcp_servers=specialist_mcp_servers)
    agent = plan.specialist if (_project_root() / ".opencode" / "agent" / f"{plan.specialist}.md").exists() else "build"
    await send_status(StatusType.SUBAGENT_SPAWNING, "Domain Agent Started", f"{plan.specialist} / {plan.selected_model}")
    result = await run_opencode(
        agent=agent,
        model=plan.selected_model,
        session_dir=session_dir,
        prompt=_domain_prompt(plan, runtime_context),
        continue_session=True,
        status_file=status_file,
        status_callback=_opencode_status,
        files=uploaded_file_paths(uploaded_files),
    )
    if result.returncode != 0:
        await send_status(StatusType.SUBAGENT_FAILED, "Domain Agent Failed", result.stderr[:500])
        raise RuntimeError(result.stderr or result.stdout)
    await send_status(StatusType.SUBAGENT_COMPLETED, "Domain Agent Completed", plan.selected_model)

    if response_path.exists():
        content = response_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        content = (result.stdout or "").strip() or "Domain task completed, but response.md was not written."

    refs = _artifact_refs(session_dir, before)
    primary, handoffs = _parse_handoffs(content)
    if handoffs and handoff_depth < 3:
        known_specialists, _ = _specialist_catalog()
        child_outputs: list[str] = []
        for handoff in handoffs:
            target = handoff["target"].strip()
            if target not in known_specialists and target != "general":
                child_outputs.append(f"[HANDOFF FAILED] No specialist available for: {target}")
                continue
            child_prompt = "\n\n".join(
                [
                    f"Handoff from `{plan.specialist}`.",
                    f"Task:\n{handoff['task']}",
                    f"Intended change:\n{handoff.get('intended_change', '')}",
                    f"Context:\n{handoff.get('context', '')}",
                    "Return concise operator-facing output if the handoff produces one. Otherwise write a terse confirmation.",
                ]
            )
            child_plan = fallback_plan(
                prompt=child_prompt,
                selected_model=plan.selected_model,
                specialist=target,
                interaction_type="domain",
                reason=f"Handoff from {plan.specialist}",
            )
            child_content, child_refs = await _run_domain(
                child_plan,
                session_dir,
                runtime_context,
                uploaded_files=uploaded_files,
                handoff_depth=handoff_depth + 1,
            )
            refs.extend(child_refs)
            if child_content.strip():
                child_outputs.append(child_content.strip())
        content = await _synthesize_handoffs(
            plan,
            session_dir,
            runtime_context,
            primary,
            child_outputs,
            uploaded_files,
        )
    elif handoffs:
        content = f"{primary}\n\n[HANDOFF FAILED] Maximum handoff depth reached.".strip()

    response_path.write_text(content, encoding="utf-8")
    return content, refs


def _snapshot_files(session_dir: Path) -> set[Path]:
    if not session_dir.exists():
        return set()
    return {p.resolve() for p in session_dir.rglob("*") if p.is_file()}


def _artifact_refs(session_dir: Path, before: set[Path]) -> list[FileRef]:
    refs: list[FileRef] = []
    for path in sorted(p for p in session_dir.rglob("*") if p.is_file()):
        rel_parts = path.relative_to(session_dir).parts
        if rel_parts and rel_parts[0].startswith("."):
            continue
        if path.name in IF_TECHNICAL_ARTIFACT_EXCLUDES:
            continue
        resolved = path.resolve()
        if resolved in before:
            continue
        rel = path.relative_to(session_dir)
        refs.append(FileRef(path=str(path), description=f"Generated artifact: {rel}"))
    return refs


async def _run_technical(
    plan: IFPlan,
    session_dir: Path,
    runtime_context: str,
    uploaded_files: list[dict[str, Any]] | None = None,
) -> tuple[str, list[FileRef]]:
    before = _snapshot_files(session_dir)
    status_file = _status_file(session_dir)
    response_path = session_dir / "response.md"
    review_path = session_dir / "review.md"
    response_path.unlink(missing_ok=True)
    review_path.unlink(missing_ok=True)
    write_opencode_config(session_dir, tool_names=[], mcp_servers=[])
    technical_prompt = f"""Use the current directory as the session workspace.

Read `history.md` for conversation context. It is incremental and edit-aware.
This directory is a persistent mount for this Discord conversation; previous files may be relevant.
Append concise progress lines to `.if/status.log` before long-running steps and after important commands.
Implement the user's request from the prompt below. Write the final user-facing answer to `response.md`.
Keep any generated deliverable files in this session directory.

Runtime context:
{runtime_context}

Prompt:
{plan.prompt}
"""
    await send_status(StatusType.SUBAGENT_SPAWNING, "Technical Build Started", plan.selected_model)
    result = await run_opencode(
        agent="build",
        model=plan.selected_model,
        session_dir=session_dir,
        prompt=technical_prompt,
        continue_session=True,
        status_file=status_file,
        status_callback=_opencode_status,
        files=uploaded_file_paths(uploaded_files),
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
        agent="planner",
        model=OPENCODE_PLANNER_MODEL,
        session_dir=session_dir,
        prompt=review_prompt,
        continue_session=True,
    )
    if review.returncode != 0:
        logger.warning("Technical review failed: %s", review.stderr[:1000])

    if review_path.exists():
        first_line = review_path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        if first_line and first_line[0].strip() == "RETRY":
            retry_prompt = f"""{technical_prompt}

Reviewer requested one retry. Review context:
{review_path.read_text(encoding="utf-8", errors="replace")}
"""
            response_path.unlink(missing_ok=True)
            retry = await run_opencode(
                agent="build",
                model=plan.selected_model,
                session_dir=session_dir,
                prompt=retry_prompt,
                continue_session=True,
                status_file=status_file,
                status_callback=_opencode_status,
                files=uploaded_file_paths(uploaded_files),
            )
            if retry.returncode != 0:
                raise RuntimeError(retry.stderr or retry.stdout)

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
    messages = request_data.get("messages") or []
    session_dir = resolve_session_dir(request_data, webhook, cache_key)
    history_events = request_data.get("_history_events")
    if not isinstance(history_events, list):
        history_events = None
    thinking_mode_requested = bool(request_data.get("_thinking_mode_requested"))
    uploaded_files = request_data.get("_uploaded_files")
    if not isinstance(uploaded_files, list):
        uploaded_files = None
    runtime_context = build_runtime_context(
        messages=messages,
        context_id=context_id,
        cache_key=cache_key,
        session_dir=session_dir,
        uploaded_files=uploaded_files,
        thinking_mode_requested=thinking_mode_requested,
    )
    try:
        plan = await _run_planner(
            session_dir,
            messages,
            history_events=history_events,
            runtime_context=runtime_context,
            uploaded_files=uploaded_files,
            thinking_mode_requested=thinking_mode_requested,
        )
    except PlannerFailure as failure:
        await send_status(StatusType.SUBAGENT_FAILED, "Planner Failed", failure.detail[:500])
        return FlowResult(content=_planner_failure_response(failure))
    if plan.thinking_mode and not thinking_mode_requested:
        runtime_context = build_runtime_context(
            messages=messages,
            context_id=context_id,
            cache_key=cache_key,
            session_dir=session_dir,
            uploaded_files=uploaded_files,
            thinking_mode_requested=True,
        )

    await send_status(
        StatusType.MODEL_SELECTED,
        "Route Selected",
        f"{plan.interaction_type} / {plan.specialist} / {plan.selected_model}",
    )

    if plan.interaction_type == "technical":
        content, refs = await _run_technical(plan, session_dir, runtime_context, uploaded_files=uploaded_files)
    elif plan.interaction_type == "domain":
        content, refs = await _run_domain(plan, session_dir, runtime_context, uploaded_files=uploaded_files)
    elif plan.thinking_mode or thinking_mode_requested:
        content, refs = await _run_domain(
            fallback_plan(
                prompt=plan.prompt,
                selected_model=plan.selected_model,
                specialist=plan.specialist if plan.specialist != "general" else "planner",
                interaction_type="domain",
                reason="Thinking mode social route",
            ),
            session_dir,
            runtime_context,
            uploaded_files=uploaded_files,
        )
    else:
        content = await _run_social(plan, http_client, runtime_context)
        refs = []

    cleaned, inline_refs = strip_files_line(content)
    refs.extend(inline_refs)
    return FlowResult(content=cleaned, file_refs=refs, plan=plan)


async def run_specialist_flow(
    *,
    specialist_slug: str,
    task: str,
    http_client: httpx.AsyncClient,
    session_dir: Path,
    context_id: str = "",
    cache_key: str = "",
    selected_model: str | None = None,
) -> tuple[str, list[FileRef]]:
    del http_client  # specialist slash commands now run through opencode
    write_history(session_dir, [{"role": "user", "content": task, "source": "direct_specialist"}])
    runtime_context = build_runtime_context(
        messages=[{"role": "user", "content": task}],
        context_id=context_id,
        cache_key=cache_key,
        session_dir=session_dir,
    )
    model_ids = load_model_ids()
    model = selected_model or (model_ids[0] if model_ids else IF_DEFAULT_DIRECT_MODEL)
    plan = fallback_plan(
        prompt=task,
        selected_model=model,
        specialist=specialist_slug,
        interaction_type="domain",
        reason=f"Direct specialist command: {specialist_slug}",
    )
    return await _run_domain(plan, session_dir, runtime_context)


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
