"""Orchestrator executor module for multi-step task execution.

This module provides the execute_plan tool for sequential multi-step plan execution
with subagents. Uses OpenHands SDK ToolDefinition pattern for proper tool registration.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Self

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

from config import (
    LLM_BASE_URL,
    OPENROUTER_API_KEY,
    ORCHESTRATOR_SUBAGENT_MODEL,
    ORCHESTRATOR_MAX_TURNS,
)
from models.router import resolve_preset_to_model, is_context_limit_error, select_model_by_context
from app_sandbox import get_local_sandbox
from files import strip_files_line, FileRef
from agent.prompts.loader import render_template

if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PlanStep:
    index: int
    title: str
    description: str
    expected_outputs: List[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    goal: str
    context: str = ""
    steps: List[PlanStep] = field(default_factory=list)


@dataclass
class StepResult:
    step_index: int
    success: bool
    summary: str = ""
    files: List[FileRef] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_message(self) -> Dict[str, Any]:
        if self.tool_calls:
            return {
                "role": "assistant",
                "content": self.content,
                "tool_calls": self.tool_calls
            }
        return {"role": "assistant", "content": self.content}


def parse_llm_response(data: Dict[str, Any]) -> LLMResponse:
    choices = data.get("choices", [])
    if not choices:
        return LLMResponse()
    
    choice = choices[0]
    message = choice.get("message", {})
    
    content = message.get("content", "") or ""
    tool_calls = []
    
    raw_tool_calls = message.get("tool_calls", [])
    for tc in raw_tool_calls:
        tool_calls.append({
            "id": tc.get("id", ""),
            "type": tc.get("type", "function"),
            "function": {
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", "{}")
            }
        })
    
    return LLMResponse(content=content, tool_calls=tool_calls)


# =============================================================================
# LLM and Subagent Functions
# =============================================================================

async def call_openrouter(
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> LLMResponse:
    # Strip SDK provider prefix — OpenRouter's raw API doesn't understand it
    model_for_api = model.removeprefix("openrouter/")

    body: Dict[str, Any] = {
        "model": model_for_api,
        "messages": messages,
        "stream": False
    }

    if tools:
        body["tools"] = [{"type": "function", "function": t} for t in tools]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    should_close = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=120.0)
        should_close = True

    try:
        resp = await http_client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=body,
            timeout=120.0,
        )
        resp.raise_for_status()
        return parse_llm_response(resp.json())
    except httpx.HTTPStatusError as e:
        logger.error(f"[OpenRouter] {e.response.status_code} for model={model_for_api}: {e.response.text[:500]}")
        raise
    finally:
        if should_close:
            await http_client.aclose()


TERMINAL_EXECUTE_SCHEMA = {
    "name": "terminal_execute",
    "description": (
        "Run a shell command in the persistent terminal. "
        "The terminal preserves state across calls. "
        "Workspace is at /home/user/workspace."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute."
            },
            "workdir": {
                "type": "string",
                "description": "Working directory. Default: /home/user/workspace",
                "default": "/home/user/workspace"
            }
        },
        "required": ["command"]
    }
}


async def run_subagent(
    system_prompt: str,
    user_message: str,
    chat_id: str,
    model: str,
    max_turns: int = ORCHESTRATOR_MAX_TURNS,
    http_client: Optional[httpx.AsyncClient] = None,
    preset_hint: Optional[str] = None,
) -> StepResult:
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tools = [TERMINAL_EXECUTE_SCHEMA]

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
                if not context_retried and preset_hint and is_context_limit_error(e):
                    fallback = select_model_by_context(preset_hint)
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
                    
                    if tool_name == "terminal_execute":
                        try:
                            args = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        
                        output = await _execute_terminal_command(
                            command=args.get("command", ""),
                            workdir=args.get("workdir", "/home/user/workspace"),
                            chat_id=chat_id,
                            http_client=http_client,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": output
                        })
                    else:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": f"Unknown tool: {tool_name}"
                        })
            else:
                content = response.content or ""
                cleaned, files = strip_files_line(content)
                
                return StepResult(
                    step_index=0,
                    success=True,
                    summary=cleaned[:500],
                    files=files,
                    error=None,
                )
        
        return StepResult(
            step_index=0,
            success=False,
            summary="",
            files=[],
            error=f"Exceeded {max_turns} turns without completion"
        )
        
    except Exception as e:
        logger.error(f"[Subagent] Error: {e}")
        return StepResult(
            step_index=0,
            success=False,
            summary="",
            files=[],
            error=f"{type(e).__name__}: {e}"
        )
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
    try:
        workspace = get_local_sandbox().get_workspace(chat_id)
        cmd_result = workspace.execute_command(command, cwd=workdir, timeout=timeout)
        result = cmd_result.stdout + (f"\n[stderr]{cmd_result.stderr}" if cmd_result.stderr else "")
        return result
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def build_subagent_prompt(
    plan: ExecutionPlan,
    step: PlanStep,
    previous: List[StepResult],
) -> str:
    return render_template(
        "subagent_step.j2",
        goal=plan.goal,
        context=plan.context,
        previous_steps=previous,
        step=step,
    )


def parse_plan(goal: str, context: str, steps: List[Dict[str, Any]]) -> ExecutionPlan:
    plan_steps = []
    for i, step_data in enumerate(steps, start=1):
        plan_steps.append(PlanStep(
            index=i,
            title=step_data.get("title", f"Step {i}"),
            description=step_data.get("description", ""),
            expected_outputs=step_data.get("expected_outputs", []),
        ))
    
    return ExecutionPlan(
        goal=goal,
        context=context,
        steps=plan_steps,
    )


# =============================================================================
# Execute Plan Tool Definition
# =============================================================================

EXECUTE_PLAN_DESCRIPTION = """Submit a structured multi-step plan for autonomous execution.

Each step is executed sequentially by a focused subagent with terminal access to the same persistent workspace. Use this for tasks requiring multiple distinct phases: clone→install→test→fix, scaffold→implement→validate, etc.

Each step sees the filesystem state left by previous steps. Steps are executed until one fails or all complete."""


class StepSchema(Action):
    """Schema for a single plan step."""
    
    title: str = Field(description="Short title for this step")
    description: str = Field(
        description="Detailed instructions. Be specific about what to do, what commands to run, what files to produce."
    )
    expected_outputs: List[str] = Field(
        default_factory=list,
        description="File paths this step should produce"
    )


class ExecutePlanAction(Action):
    """Action for executing a multi-step plan."""
    
    goal: str = Field(description="What the overall task achieves")
    context: str = Field(
        default="",
        description="Shared context all steps need (repo URL, language, constraints)"
    )
    steps: List[StepSchema] = Field(
        description="List of steps to execute sequentially"
    )
    
    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action."""
        content = Text()
        content.append("Execute plan:\n", style="bold blue")
        content.append(f"Goal: {self.goal}\n", style="green")
        content.append(f"Steps: {len(self.steps)}\n", style="dim")
        for i, step in enumerate(self.steps, 1):
            content.append(f"  {i}. {step.title}\n", style="yellow")
        return content


class ExecutePlanObservation(TextObservation):
    """Observation from plan execution."""
    
    result: str = Field(default="", description="Execution result summary")
    steps_completed: int = Field(default=0, description="Number of steps completed")
    steps_total: int = Field(default=0, description="Total number of steps")
    success: bool = Field(default=True, description="Whether all steps completed")
    
    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this observation."""
        content = Text()
        content.append("Plan execution result:\n", style="bold blue")
        content.append(f"Completed: {self.steps_completed}/{self.steps_total}\n", style="green")
        content.append(self.result)
        return content


class ExecutePlanExecutor(ToolExecutor):
    """Executor for plan execution."""
    
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
    
    def __call__(
        self,
        action: ExecutePlanAction,
        conversation: Any = None,
    ) -> ExecutePlanObservation:
        """Execute the plan."""
        async def _run():
            # Create http_client inside the async context
            async with httpx.AsyncClient(timeout=120.0) as http_client:
                return await _execute_plan_impl(
                    goal=action.goal,
                    context=action.context,
                    steps=[s.model_dump() for s in action.steps],
                    chat_id=self.chat_id,
                    http_client=http_client,
                )
        
        # Handle async in sync context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result, completed, total, success = pool.submit(asyncio.run, _run()).result()
        else:
            result, completed, total, success = asyncio.run(_run())
        
        return ExecutePlanObservation(
            result=result,
            steps_completed=completed,
            steps_total=total,
            success=success,
        )


class ExecutePlanTool(ToolDefinition[ExecutePlanAction, ExecutePlanObservation]):
    """Tool for executing multi-step plans."""
    
    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence[Self]:
        """Create ExecutePlanTool instance."""
        # Note: http_client is NOT passed - it's created inside the executor
        # This avoids serialization issues with httpx.AsyncClient in Tool params
        return [
            cls(
                action_type=ExecutePlanAction,
                observation_type=ExecutePlanObservation,
                description=EXECUTE_PLAN_DESCRIPTION,
                executor=ExecutePlanExecutor(chat_id=chat_id),
                annotations=ToolAnnotations(
                    title="execute_plan",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
        ]


# Register the tool
register_tool("execute_plan", ExecutePlanTool)


# =============================================================================
# Internal Implementation Function
# =============================================================================

async def _execute_plan_impl(
    goal: str,
    steps: List[Dict[str, Any]],
    context: str,
    chat_id: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> tuple[str, int, int, bool]:
    """Internal implementation of plan execution.
    
    Returns:
        Tuple of (result_text, steps_completed, steps_total, success)
    """
    logger.info(f"[Orchestrator] Starting plan execution: {goal}")
    
    plan = parse_plan(goal, context, steps)
    results: List[StepResult] = []
    
    should_close = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=120.0)
        should_close = True
    
    try:
        for step in plan.steps:
            logger.info(f"[Orchestrator] Executing step {step.index}: {step.title}")
            
            prompt = build_subagent_prompt(plan, step, results)
            result = await run_subagent(
                system_prompt=prompt,
                user_message=f"Execute: {step.title}\n\n{step.description}",
                chat_id=chat_id,
                model=resolve_preset_to_model(ORCHESTRATOR_SUBAGENT_MODEL),
                max_turns=ORCHESTRATOR_MAX_TURNS,
                http_client=http_client,
                preset_hint=ORCHESTRATOR_SUBAGENT_MODEL,
            )
            
            result.step_index = step.index
            results.append(result)
            
            if not result.success:
                logger.warning(f"[Orchestrator] Step {step.index} failed: {result.error}")
                break
            
            logger.info(f"[Orchestrator] Step {step.index} completed: {result.summary[:100]}")
        
        completed = len([r for r in results if r.success])
        total = len(plan.steps)
        success = completed == total
        
        lines = [
            f"Plan execution: {completed}/{total} steps completed."
        ]
        
        for r in results:
            mark = "✓" if r.success else "✗"
            lines.append(f"  [{mark}] Step {r.step_index}: {r.summary[:200]}")
            if r.files:
                for f in r.files:
                    lines.append(f"      → {f.path} ({f.description})")
            if r.error:
                lines.append(f"      ERROR: {r.error}")
        
        return "\n".join(lines), completed, total, success
        
    except Exception as e:
        logger.error(f"[Orchestrator] Plan execution error: {e}")
        return f"Plan execution failed: {type(e).__name__}: {e}", 0, len(plan.steps), False
    finally:
        if should_close:
            await http_client.aclose()


# =============================================================================
# Legacy async function for backwards compatibility
# =============================================================================

async def execute_plan(
    goal: str,
    steps: List[Dict[str, Any]],
    context: str = "",
    *,
    chat_id: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Execute a multi-step plan with subagents.
    
    This function is kept for backwards compatibility.
    """
    result, _, _, _ = await _execute_plan_impl(
        goal=goal,
        context=context,
        steps=steps,
        chat_id=chat_id,
        http_client=http_client,
    )
    return result


# =============================================================================
# Tool Registration Helper
# =============================================================================

def get_orchestrator_tools(
    chat_id: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[Tool]:
    """Get orchestrator tool specifications for Agent initialization.
    
    This returns Tool specs that reference the registered tools.
    The actual tool instances are created by the ToolDefinition.create() method.
    
    Note: http_client is NOT passed in params to avoid serialization issues.
    The executor creates its own http_client when needed.
    
    Args:
        chat_id: Chat/session ID for terminal container scoping
        http_client: Optional shared HTTP client (UNUSED - kept for API compatibility)
        
    Returns:
        List of Tool specs for Agent initialization
    """
    return [
        Tool(name="execute_plan", params={"chat_id": chat_id}),
    ]


# Schema export for backwards compatibility
EXECUTE_PLAN_SCHEMA = {
    "name": "execute_plan",
    "description": EXECUTE_PLAN_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "What the overall task achieves."
            },
            "context": {
                "type": "string",
                "description": "Shared context all steps need (repo URL, language, constraints)."
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {
                            "type": "string",
                            "description": "Detailed instructions. Be specific about what to do, what commands to run, what files to produce."
                        },
                        "expected_outputs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "File paths this step should produce."
                        }
                    },
                    "required": ["title", "description"]
                }
            }
        },
        "required": ["goal", "steps"]
    }
}
