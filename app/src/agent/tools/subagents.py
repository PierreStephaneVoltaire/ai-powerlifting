"""Subagent spawning tools for specialist delegation.

This module provides tools for the main agent to delegate work to
specialized subagents:

- deep_think: Extended pondering on complex topics
- spawn_specialist: Delegate to a domain specialist
- spawn_specialists: Parallel delegation to multiple specialists

Each tool resolves appropriate directives, renders templates, and
spawns a subagent with the configured preset and tools.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx
from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from openhands.sdk import Tool, register_tool
from agent.tools.base import TextObservation

from agent.tools.subagent_sdk import run_subagent_sdk

from app_sandbox import get_local_sandbox
from config import (
    LLM_BASE_URL,
    OPENROUTER_API_KEY,
    THINKING_PRESET,
    THINKING_MAX_TURNS,
    SPECIALIST_PRESET,
    SPECIALIST_MAX_TURNS,
)
from storage.factory import get_directive_store
from agent.specialists import (
    get_specialist,
    list_specialists,
    render_specialist_prompt,
    SKILLS,
)
from orchestrator.executor import call_openrouter, TERMINAL_EXECUTE_SCHEMA

if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

logger = logging.getLogger(__name__)


def _is_external_tool(tool_name: str) -> bool:
    """Check if a tool name is registered in the external tool registry."""
    try:
        from agent.tool_registry import get_tool_registry
        return get_tool_registry().has_tool(tool_name)
    except Exception:
        return False


# =============================================================================
# Directive Resolution
# =============================================================================

def _resolve_directives(
    directive_types: List[str],
    extra_directives: Optional[str] = None
) -> str:
    """Resolve and format directives for a subagent.

    Gets tier 0 directives plus directives matching any of the given types,
    excluding main-agent-only types (tool, memory, metacognition).

    Args:
        directive_types: Types of directives to include (e.g., ["code", "security"])
        extra_directives: Additional raw directive text to include

    Returns:
        Formatted directive block string
    """
    try:
        store = get_directive_store()
        directives = store.get_for_subagent(directive_types)
        formatted = store.format_directives(directives)

        if extra_directives:
            if formatted:
                formatted = f"{formatted}\n\n{extra_directives}"
            else:
                formatted = extra_directives

        return formatted

    except Exception as e:
        logger.warning(f"[Subagents] Failed to resolve directives: {e}")
        return extra_directives or ""


# =============================================================================
# Subagent Execution
# =============================================================================

async def _run_subagent(
    system_prompt: str,
    user_message: str,
    model: str,
    max_turns: int,
    chat_id: str,
    tool_schemas: Optional[List[Dict[str, Any]]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    original_preset: Optional[str] = None,
) -> str:
    """Run a subagent with the given configuration.

    Args:
        system_prompt: Full system prompt for the subagent
        user_message: Task description
        model: OpenRouter model/preset slug
        max_turns: Maximum turns before timeout
        chat_id: Chat ID for terminal container scoping
        tool_schemas: Optional domain tool schemas (health, finance, etc.)
        http_client: Optional shared HTTP client

    Returns:
        Subagent response text
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tools = list(tool_schemas) if tool_schemas else [TERMINAL_EXECUTE_SCHEMA]

    should_close = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=120.0)
        should_close = True

    context_retried = False

    try:
        for turn in range(max_turns):
            logger.debug(f"[Subagent] Turn {turn + 1}/{max_turns}")

            try:
                response = await call_openrouter(
                    model=model,
                    messages=messages,
                    tools=tools,
                    http_client=http_client,
                )
            except Exception as e:
                from models.router import is_context_limit_error, select_model_by_context
                if not context_retried and original_preset and is_context_limit_error(e):
                    fallback = select_model_by_context(original_preset)
                    if fallback and fallback != model:
                        logger.warning(f"[Subagent] Context limit, retrying with {fallback}")
                        model = fallback
                        context_retried = True
                        continue
                raise

            if response.tool_calls:
                messages.append(response.to_message())

                for tc in response.tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    tool_id = tc.get("id", "")

                    import json
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}

                    if tool_name == "terminal_execute":
                        output = await _execute_terminal_command(
                            command=args.get("command", ""),
                            workdir=args.get("workdir", "/home/user/workspace"),
                            chat_id=chat_id,
                            http_client=http_client,
                        )
                    elif tool_name == "get_current_date":
                        from agent.tools.context_tools import get_current_date
                        import json as _json
                        output = _json.dumps(get_current_date())
                    elif tool_name in ("plan_append", "plan_read", "plan_list", "plan_grep"):
                        from agent.tools.planfiles import _execute_plan_tool_sync
                        output = _execute_plan_tool_sync(tool_name, chat_id, args)
                    elif _is_external_tool(tool_name):
                        from agent.tools.tool_schemas import execute_domain_tool
                        output = await execute_domain_tool(tool_name, args)
                    else:
                        output = f"Unknown tool: {tool_name}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": output
                    })
            else:
                content = response.content if response.content else None
                if not content:
                    logger.warning(f"[Subagent] Specialist returned empty response after {turn + 1} turns")
                    return "[SUBAGENT ERROR] Specialist returned an empty response."
                return content

        return f"Subagent exceeded {max_turns} turns without completion"

    except Exception as e:
        logger.error(f"[Subagent] Error: {e}")
        return f"Subagent error: {type(e).__name__}: {e}"
    finally:
        if should_close:
            await http_client.aclose()


async def _execute_terminal_command(
    command: str,
    workdir: str,
    chat_id: str,
    http_client: httpx.AsyncClient,
    timeout: float = 120.0,
) -> str:
    """Execute a terminal command for a subagent."""
    try:
        workspace = get_local_sandbox().get_workspace(chat_id)
        cmd_result = workspace.execute_command(command, cwd=workdir, timeout=timeout)
        result = cmd_result.stdout + (f"\n[stderr]{cmd_result.stderr}" if cmd_result.stderr else "")
        return result
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


# =============================================================================
# Deep Think Tool
# =============================================================================

DEEP_THINK_DESCRIPTION = """Spawn a deep thinking subagent for extended analysis.

Use this for complex problems that require methodical reasoning, planning,
or thorough analysis. The subagent takes time to think through the problem
and produces detailed output.

The result is typically saved to plans/{topic}-plan.md for later reference."""


class DeepThinkAction(Action):
    """Action for deep thinking subagent."""

    topic: str = Field(
        description="Short topic identifier for the thinking task (used in output filename)"
    )
    task: str = Field(
        description="Detailed description of what to think about or analyze"
    )
    context: str = Field(
        default="",
        description="Background information relevant to the task"
    )
    extra_directives: str = Field(
        default="",
        description="Additional directive text to include beyond tier 0 directives"
    )


class DeepThinkObservation(TextObservation):
    """Observation from deep thinking subagent."""

    result: str = Field(default="", description="Analysis or plan produced")
    topic: str = Field(default="", description="Topic identifier")
    file_path: str = Field(default="", description="Path where result was saved")

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Deep Think Result:\n", style="bold blue")
        content.append(f"Topic: {self.topic}\n", style="green")
        if self.file_path:
            content.append(f"Saved to: {self.file_path}\n", style="dim")
        content.append(self.result)
        return content


class DeepThinkExecutor(ToolExecutor):
    """Executor for deep thinking subagent."""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    def __call__(
        self,
        action: DeepThinkAction,
        conversation: Any = None,
    ) -> DeepThinkObservation:
        async def _run():
            # Resolve directives (tier 0 only for deep thinking)
            directives = _resolve_directives(["core"], action.extra_directives)

            # Render template
            from agent.prompts.loader import render_template
            system_prompt = render_template(
                "deep_thinker.j2",
                task=action.task,
                context=action.context,
                directives=directives,
            )

            # Add file output instruction
            file_path = f"plans/{action.topic}-plan.md"
            user_message = f"{action.task}\n\nSave your analysis to: {file_path}"

            # Route to concrete model via router
            from models.router import select_model_for_specialist
            model = await select_model_for_specialist(THINKING_PRESET, action.task)

            async with httpx.AsyncClient(timeout=120.0) as http_client:
                result = await _run_subagent(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=model,
                    max_turns=THINKING_MAX_TURNS,
                    chat_id=self.chat_id,
                    http_client=http_client,
                    original_preset=THINKING_PRESET,
                )

            return result, file_path

        # Handle async in sync context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import contextvars
            ctx = contextvars.copy_context()
            with ThreadPoolExecutor() as pool:
                result, file_path = pool.submit(ctx.run, asyncio.run, _run()).result()
        else:
            result, file_path = asyncio.run(_run())

        return DeepThinkObservation(
            result=result,
            topic=action.topic,
            file_path=file_path,
        )


class DeepThinkTool(ToolDefinition[DeepThinkAction, DeepThinkObservation]):
    """Tool for spawning deep thinking subagent."""

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence["DeepThinkTool"]:
        return [
            cls(
                action_type=DeepThinkAction,
                observation_type=DeepThinkObservation,
                description=DEEP_THINK_DESCRIPTION,
                executor=DeepThinkExecutor(chat_id=chat_id),
                annotations=ToolAnnotations(
                    title="deep_think",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


register_tool("deep_think", DeepThinkTool)


# =============================================================================
# Spawn Specialist Tool
# =============================================================================

SPAWN_SPECIAListDescription = """Spawn a specialist subagent for domain-specific work.

Available specialists:
- coder: General software engineering (writing code, features, modifications)
- scripter: Quick tasks completable in 3-5 commands (files, scripts, one-liners)
- debugger: Deep code debugging and error analysis
- architect: System architecture and design patterns
- secops: Security operations and vulnerability analysis
- devops: Infrastructure and deployment automation
- financial_analyst: Financial data analysis and market research
- health_write: DynamoDB mutations for training program (logging sessions, updating body weight, RPE, etc.)
- research_assistant: Up-to-date research via native web search + local supplement corpus

Skills (mode modifiers):
- red_team: Adversarial/attack perspective
- blue_team: Defensive/protection perspective
- pro_con: Balanced pros and cons analysis"""


class SpawnSpecialistAction(Action):
    """Action for spawning a specialist subagent."""

    specialist_type: str = Field(
        description="Type of specialist to spawn (coder, scripter, debugger, architect, secops, devops, financial_analyst, health_write, research_assistant)"
    )
    task: str = Field(
        description="Detailed task description for the specialist"
    )
    context: str = Field(
        default="",
        description="Background information for the specialist"
    )
    extra_directives: str = Field(
        default="",
        description="Additional directive text beyond the specialist's default types"
    )
    skill: Optional[str] = Field(
        default=None,
        description="Optional skill mode: red_team, blue_team, pro_con, steelman, devils_advocate, backcast, rubber_duck, eli5, formal, speed, teach"
    )
    write_to_file: Optional[str] = Field(
        default=None,
        description="Optional file path to save the specialist's output"
    )
    pk: Optional[str] = Field(
        default="operator",
        description="Primary key for DynamoDB operations (default: operator)"
    )
    sk: Optional[str] = Field(
        default="program#current",
        description="Sort key for DynamoDB operations (default: program#current)"
    )


class SpawnSpecialistObservation(TextObservation):
    """Observation from specialist subagent."""

    result: str = Field(default="", description="Specialist's output")
    specialist_type: str = Field(default="", description="Specialist that was spawned")
    skill: Optional[str] = Field(default=None, description="Skill mode used")

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append(f"Specialist Result ({self.specialist_type}):\n", style="bold blue")
        if self.skill:
            content.append(f"Skill: {self.skill}\n", style="yellow")
        content.append(self.result)
        return content


class SpawnSpecialistExecutor(ToolExecutor):
    """Executor for specialist subagent."""

    def __init__(self, chat_id: str, model_override: Optional[str] = None):
        self.chat_id = chat_id
        self.model_override = model_override.strip() if model_override else None

    def __call__(
        self,
        action: SpawnSpecialistAction,
        conversation: Any = None,
    ) -> SpawnSpecialistObservation:
        async def _run():
            # Get specialist config
            specialist = get_specialist(action.specialist_type)
            if not specialist:
                return f"Unknown specialist type: {action.specialist_type}. Available: {[s.slug for s in list_specialists()]}", None

            # Validate skill
            if action.skill and action.skill not in SKILLS:
                return f"Unknown skill: {action.skill}. Available: {SKILLS}", None

            logger.info(f"[Subagents] Spawning: slug={action.specialist_type} | skill={action.skill} | task={action.task[:100]}")

            # Resolve directives
            directives = _resolve_directives(
                specialist.directive_types,
                action.extra_directives
            )

            # Resolve context builder
            injected_context: Optional[str] = None
            if specialist.context_builder:
                try:
                    module_path, func_name = specialist.context_builder.rsplit(":", 1)
                    import importlib
                    mod = importlib.import_module(module_path)
                    builder = getattr(mod, func_name)
                    injected_context = await builder(pk=action.pk or "operator", task=action.task)
                except Exception as e:
                    logger.warning(f"[SpecialistContext] context_builder failed for {specialist.slug}: {e}")

            # Render specialist prompt
            system_prompt = render_specialist_prompt(
                specialist=specialist,
                task=action.task,
                context=action.context,
                directives=directives,
                skill=action.skill,
                pk=action.pk,
                sk=action.sk,
                injected_context=injected_context,
            )

            # Build user message
            user_message = action.task
            if action.write_to_file:
                user_message = f"{action.task}\n\nSave your output to: {action.write_to_file}"

            # Route to concrete model via router unless an internal caller pins
            # a cheaper helper model for narrow UI tasks.
            if self.model_override:
                model = self.model_override
            else:
                from models.router import select_model_for_specialist
                model = await select_model_for_specialist(specialist.preset, action.task)

            from channels.status import send_status, StatusType
            await send_status(
                StatusType.SUBAGENT_SPAWNING,
                f"Spawning: {specialist.slug}",
                action.task[:100],
                {"Model": model},
            )
            await send_status(
                StatusType.MODEL_SELECTED,
                f"Router: {model}",
                model,
            )

            # Route to SDK agentic loop for agentic specialists
            if specialist.agentic:
                result = await run_subagent_sdk(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=model,
                    max_turns=specialist.max_turns,
                    chat_id=self.chat_id,
                    tool_names=specialist.tools,
                    skill_names=getattr(specialist, "skills", []),
                    original_preset=specialist.preset,
                )
            else:
                # Non-agentic: use raw OpenRouter path
                from agent.tools.tool_schemas import get_schemas_for_specialist
                tool_schemas = get_schemas_for_specialist(specialist.tools)

                async with httpx.AsyncClient(timeout=120.0) as http_client:
                    result = await _run_subagent(
                        system_prompt=system_prompt,
                        user_message=user_message,
                        model=model,
                        max_turns=specialist.max_turns,
                        chat_id=self.chat_id,
                        tool_schemas=tool_schemas,
                        http_client=http_client,
                        original_preset=specialist.preset,
                    )

            logger.info(f"[Subagents] Completed: slug={specialist.slug} | result_len={len(result)}")

            from channels.status import send_status, StatusType
            await send_status(StatusType.SUBAGENT_COMPLETED, f"Completed: {specialist.slug}")

            return result, specialist.slug

        # Handle async in sync context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import contextvars
            ctx = contextvars.copy_context()
            with ThreadPoolExecutor() as pool:
                result, slug = pool.submit(ctx.run, asyncio.run, _run()).result()
        else:
            result, slug = asyncio.run(_run())

        # Handle error case
        if slug is None:
            return SpawnSpecialistObservation(
                result=result,
                specialist_type=action.specialist_type,
                skill=action.skill,
            )

        return SpawnSpecialistObservation(
            result=result,
            specialist_type=slug,
            skill=action.skill,
        )


SPAWN_SPECIALIST_DESCRIPTION = """Spawn a single specialist subagent to handle a specific task.

Use this when you need expert help in a specific domain. The specialist will
work independently and return results.

Available specialists include: coder, scripter, debugger, architect, secops, devops.
Choose the specialist that best matches your task."""


class SpawnSpecialistTool(ToolDefinition[SpawnSpecialistAction, SpawnSpecialistObservation]):
    """Tool for spawning specialist subagent."""

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence["SpawnSpecialistTool"]:
        return [
            cls(
                action_type=SpawnSpecialistAction,
                observation_type=SpawnSpecialistObservation,
                description=SPAWN_SPECIALIST_DESCRIPTION,
                executor=SpawnSpecialistExecutor(chat_id=chat_id),
                annotations=ToolAnnotations(
                    title="spawn_specialist",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


register_tool("spawn_specialist", SpawnSpecialistTool)


# =============================================================================
# Spawn Specialists (Parallel) Tool
# =============================================================================

SPAWN_SPECIALISTS_DESCRIPTION = """Spawn multiple specialist subagents in parallel.

Use this when you need multiple perspectives on the same task simultaneously.
Each specialist works independently and their results are combined.

Example: Spawn debugger + secops to analyze code for both bugs and security issues."""


class SpawnSpecialistsAction(Action):
    """Action for spawning multiple specialists in parallel."""

    specialist_types: List[str] = Field(
        description="List of specialist types to spawn in parallel (e.g., ['debugger', 'secops'])"
    )
    task: str = Field(
        description="Task description - same task sent to all specialists"
    )
    context: str = Field(
        default="",
        description="Background information - same context sent to all specialists"
    )


class SpawnSpecialistsObservation(TextObservation):
    """Observation from parallel specialist execution."""

    results: str = Field(default="", description="Combined results from all specialists")
    specialist_types: List[str] = Field(default_factory=list, description="Specialists that were spawned")

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Parallel Specialists Results:\n", style="bold blue")
        content.append(f"Specialists: {', '.join(self.specialist_types)}\n", style="green")
        content.append(self.results)
        return content


class SpawnSpecialistsExecutor(ToolExecutor):
    """Executor for parallel specialist execution."""

    def __init__(self, chat_id: str):
        self.chat_id = chat_id

    def __call__(
        self,
        action: SpawnSpecialistsAction,
        conversation: Any = None,
    ) -> SpawnSpecialistsObservation:
        async def _run():
            async with httpx.AsyncClient(timeout=120.0) as http_client:
                tasks = []
                valid_specialists = []

                logger.info(f"[Subagents] Spawning parallel: slugs={action.specialist_types} | task={action.task[:100]}")
                from agent.tools.tool_schemas import get_schemas_for_specialist
                from models.router import select_model_for_specialist
                for slug in action.specialist_types:
                    specialist = get_specialist(slug)
                    if not specialist:
                        logger.warning(f"[Subagents] Unknown specialist: {slug}")
                        continue

                    valid_specialists.append(specialist)

                    # Resolve directives
                    directives = _resolve_directives(specialist.directive_types)

                    # Render prompt
                    system_prompt = render_specialist_prompt(
                        specialist=specialist,
                        task=action.task,
                        context=action.context,
                        directives=directives,
                    )

                    # Route to concrete model via router
                    model = await select_model_for_specialist(specialist.preset, action.task)

                    if specialist.agentic:
                        tasks.append(run_subagent_sdk(
                            system_prompt=system_prompt,
                            user_message=action.task,
                            model=model,
                            max_turns=specialist.max_iterations,
                            chat_id=self.chat_id,
                            tool_names=specialist.tools,
                        ))
                    else:
                        tool_schemas = get_schemas_for_specialist(specialist.tools)
                        tasks.append(_run_subagent(
                            system_prompt=system_prompt,
                            user_message=action.task,
                            model=model,
                            max_turns=specialist.max_turns,
                            chat_id=self.chat_id,
                            tool_schemas=tool_schemas,
                            http_client=http_client,
                        ))

                if not tasks:
                    return "No valid specialists to spawn", []

                # Run all specialists in parallel
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Combine results
                combined = []
                for specialist, result in zip(valid_specialists, results):
                    if isinstance(result, Exception):
                        combined.append(f"## {specialist.slug}\n\nError: {type(result).__name__}: {result}")
                    else:
                        combined.append(f"## {specialist.slug}\n\n{result}")

                logger.info(f"[Subagents] Parallel completed: slugs={[s.slug for s in valid_specialists]} | results={len(combined)}")
                return "\n\n---\n\n".join(combined), [s.slug for s in valid_specialists]

        # Handle async in sync context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import contextvars
            ctx = contextvars.copy_context()
            with ThreadPoolExecutor() as pool:
                results, slugs = pool.submit(ctx.run, asyncio.run, _run()).result()
        else:
            results, slugs = asyncio.run(_run())

        return SpawnSpecialistsObservation(
            results=results,
            specialist_types=slugs,
        )


class SpawnSpecialistsTool(ToolDefinition[SpawnSpecialistsAction, SpawnSpecialistsObservation]):
    """Tool for spawning multiple specialists in parallel."""

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence["SpawnSpecialistsTool"]:
        return [
            cls(
                action_type=SpawnSpecialistsAction,
                observation_type=SpawnSpecialistsObservation,
                description=SPAWN_SPECIALISTS_DESCRIPTION,
                executor=SpawnSpecialistsExecutor(chat_id=chat_id),
                annotations=ToolAnnotations(
                    title="spawn_specialists",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


register_tool("spawn_specialists", SpawnSpecialistsTool)


# =============================================================================
# list_specialists tool
# =============================================================================

LIST_SPECIALISTS_DESCRIPTION = """List all available specialist subagents with their descriptions.
Returns a formatted list of specialist slugs and descriptions so the main agent
can pick the most appropriate specialist for the current task.

IMPORTANT constraints (included in output):
- health_write and finance_write are HANDOFF-ONLY — never select them directly
- media_reader should only be used for image/file attachments requiring vision analysis"""


class ListSpecialistsAction(Action):
    pass


class ListSpecialistsObservation(TextObservation):
    specialists: str = Field(default="", description="Formatted list of available specialists")

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Available Specialists:\n", style="bold blue")
        content.append(self.specialists, style="green")
        return content


class ListSpecialistsExecutor(ToolExecutor):
    def __call__(
        self,
        action: ListSpecialistsAction,
        conversation: Any = None,
    ) -> ListSpecialistsObservation:
        specialists = list_specialists()
        handoff_only = {"health_write", "finance_write"}

        lines = []
        for s in specialists:
            if s.slug in handoff_only:
                continue
            desc = s.description.strip().replace("\n", " ").split(".")[0]
            lines.append(f"- {s.slug}: {desc}.")

        result = "\n".join(lines)
        result += "\n\nCONSTRAINTS:"
        result += "\n- Do NOT select health_write or finance_write — they are used only via HANDOFF_REQUIRED from other specialists."
        result += "\n- Use media_reader ONLY when the message contains an image or file attachment that requires vision analysis."

        return ListSpecialistsObservation(specialists=result)


class ListSpecialistsTool(ToolDefinition[ListSpecialistsAction, ListSpecialistsObservation]):
    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence["ListSpecialistsTool"]:
        return [
            cls(
                action_type=ListSpecialistsAction,
                observation_type=ListSpecialistsObservation,
                description=LIST_SPECIALISTS_DESCRIPTION,
                executor=ListSpecialistsExecutor(),
                annotations=ToolAnnotations(
                    title="list_specialists",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


register_tool("list_specialists", ListSpecialistsTool)


# =============================================================================
# condense_intent tool
# =============================================================================

CONDENSE_INTENT_DESCRIPTION = """Rewrite the user's message as a focused task for a specialist.
Strips social elements and produces a concise, actionable prompt. The output
should be passed directly to spawn_specialist."""


class CondenseIntentAction(Action):
    last_message: str = Field(description="The user's last message")
    specialist_type: str = Field(description="The specialist type to condense intent for")
    context_summary: str = Field(default="", description="Relevant context from conversation history")


class CondenseIntentObservation(TextObservation):
    condensed_prompt: str = Field(default="", description="Focused task description for specialist")

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Condensed Intent:\n", style="bold blue")
        content.append(self.condensed_prompt, style="green")
        return content


class CondenseIntentExecutor(ToolExecutor):
    def __call__(
        self,
        action: CondenseIntentAction,
        conversation: Any = None,
    ) -> CondenseIntentObservation:
        from config import CONDENSE_INTENT_MODEL
        from agent.prompts.loader import render_template

        async def _run():
            prompt = render_template(
                "condense_intent.j2",
                last_message=action.last_message,
                specialist_type=action.specialist_type,
                context_summary=action.context_summary,
            )
            try:
                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    response = await call_openrouter(
                        model=CONDENSE_INTENT_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        tools=None,
                        http_client=http_client,
                    )
                return CondenseIntentObservation(
                    condensed_prompt=response.content.strip()
                )
            except Exception as e:
                logger.warning(f"[CondenseIntent] Failed: {e}, using raw message")
                return CondenseIntentObservation(
                    condensed_prompt=action.last_message[:500]
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            with ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, _run()).result()
        return asyncio.run(_run())


class CondenseIntentTool(ToolDefinition[CondenseIntentAction, CondenseIntentObservation]):
    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence["CondenseIntentTool"]:
        return [
            cls(
                action_type=CondenseIntentAction,
                observation_type=CondenseIntentObservation,
                description=CONDENSE_INTENT_DESCRIPTION,
                executor=CondenseIntentExecutor(),
                annotations=ToolAnnotations(
                    title="condense_intent",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]


register_tool("condense_intent", CondenseIntentTool)


# =============================================================================
# Tool Registration Helper
# =============================================================================

def get_subagent_tools(chat_id: str) -> List[Tool]:
    """Get subagent tool specifications for Agent initialization.

    Args:
        chat_id: Chat/session ID for terminal container scoping

    Returns:
        List of Tool specs for Agent initialization
    """
    return [
        Tool(name="list_specialists", params={}),
        Tool(name="condense_intent", params={}),
        Tool(name="deep_think", params={"chat_id": chat_id}),
        Tool(name="spawn_specialist", params={"chat_id": chat_id}),
        Tool(name="spawn_specialists", params={"chat_id": chat_id}),
    ]
