"""Orchestrator analyzer module for parallel code analysis.

This module provides the analyze_parallel tool for spawning parallel analysis
subagents that review code from multiple perspectives. Uses OpenHands SDK
ToolDefinition pattern for proper tool registration.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
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

from config import (
    ORCHESTRATOR_ANALYSIS_MODEL,
    ORCHESTRATOR_SYNTHESIS_MODEL,
    ORCHESTRATOR_ANALYSIS_MAX_TURNS,
)
from models.router import resolve_preset_to_model
from app_sandbox import get_local_sandbox
from agent.prompts.loader import render_template, load_prompt

from .executor import run_subagent, StepResult

if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState

logger = logging.getLogger(__name__)


# =============================================================================
# Perspective Prompts
# =============================================================================

def _load_perspective_prompts() -> Dict[str, str]:
    """Load all perspective prompt templates."""
    return {
        p: load_prompt(f"analyzer_{p}.j2")
        for p in ("security", "performance", "architecture", "testing", "documentation")
    }

PERSPECTIVE_PROMPTS: Dict[str, str] = _load_perspective_prompts()


# =============================================================================
# Analyze Parallel Tool Definition
# =============================================================================

ANALYZE_PARALLEL_DESCRIPTION = """Spawn parallel analysis subagents that each review code/context from different perspectives.

Results are written to /home/user/workspace/findings/, then a synthesizer combines them.

Available perspectives:
- security: Input validation, injection vectors, auth/authz gaps, hardcoded secrets
- performance: Algorithmic complexity, database patterns, memory usage, I/O issues
- architecture: Coupling, abstractions, error handling, testability, scalability
- testing: Test coverage gaps, edge cases, test quality, integration vs unit balance
- documentation: Docstrings, README accuracy, API docs, naming clarity

The synthesizer creates a prioritized report with recommended action plan."""


class AnalyzeParallelAction(Action):
    """Action for parallel code analysis."""
    
    context: str = Field(description="What to analyze and any specific concerns")
    target_paths: List[str] = Field(
        default_factory=list,
        description="Workspace paths to focus on. Subagents can also explore freely."
    )
    perspectives: List[str] = Field(
        default_factory=lambda: ["security", "performance", "architecture"],
        description="Which perspectives to use. Default: ['security', 'performance', 'architecture']"
    )
    
    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action."""
        content = Text()
        content.append("Analyze parallel:\n", style="bold blue")
        content.append(f"Context: {self.context[:100]}...\n", style="green")
        content.append(f"Perspectives: {', '.join(self.perspectives)}\n", style="yellow")
        if self.target_paths:
            content.append(f"Targets: {', '.join(self.target_paths)}", style="dim")
        return content


class AnalyzeParallelObservation(Observation):
    """Observation from parallel analysis."""
    
    result: str = Field(default="", description="Analysis result summary")
    report_path: str = Field(
        default="/home/user/workspace/findings/synthesized.md",
        description="Path to synthesized report"
    )
    perspectives_succeeded: int = Field(default=0, description="Number of perspectives that succeeded")
    perspectives_total: int = Field(default=0, description="Total number of perspectives")
    success: bool = Field(default=True, description="Whether analysis completed")
    
    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this observation."""
        content = Text()
        content.append("Analysis result:\n", style="bold blue")
        content.append(f"Succeeded: {self.perspectives_succeeded}/{self.perspectives_total}\n", style="green")
        content.append(f"Report: {self.report_path}\n", style="yellow")
        content.append(self.result)
        return content


class AnalyzeParallelExecutor(ToolExecutor):
    """Executor for parallel analysis."""
    
    def __init__(self, chat_id: str, http_client: Optional[httpx.AsyncClient] = None):
        self.chat_id = chat_id
        self.http_client = http_client
    
    def __call__(
        self,
        action: AnalyzeParallelAction,
        conversation: Any = None,
    ) -> AnalyzeParallelObservation:
        """Execute the parallel analysis."""
        async def _run():
            return await _analyze_parallel_impl(
                context=action.context,
                target_paths=action.target_paths,
                perspectives=action.perspectives,
                chat_id=self.chat_id,
                http_client=self.http_client,
            )
        
        # Handle async in sync context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result, succeeded, total, success = pool.submit(asyncio.run, _run()).result()
        else:
            result, succeeded, total, success = asyncio.run(_run())
        
        return AnalyzeParallelObservation(
            result=result,
            perspectives_succeeded=succeeded,
            perspectives_total=total,
            success=success,
        )


class AnalyzeParallelTool(ToolDefinition[AnalyzeParallelAction, AnalyzeParallelObservation]):
    """Tool for parallel code analysis from multiple perspectives."""
    
    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,
        chat_id: str = "",
        **params,
    ) -> Sequence[Self]:
        """Create AnalyzeParallelTool instance."""
        return [
            cls(
                action_type=AnalyzeParallelAction,
                observation_type=AnalyzeParallelObservation,
                description=ANALYZE_PARALLEL_DESCRIPTION,
                executor=AnalyzeParallelExecutor(
                    chat_id=chat_id,
                    http_client=params.get("http_client"),
                ),
                annotations=ToolAnnotations(
                    title="analyze_parallel",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        ]


# Register the tool
register_tool("analyze_parallel", AnalyzeParallelTool)


# =============================================================================
# Internal Implementation Function
# =============================================================================

async def _analyze_parallel_impl(
    context: str,
    target_paths: List[str],
    perspectives: List[str],
    chat_id: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> tuple[str, int, int, bool]:
    """Internal implementation of parallel analysis.
    
    Returns:
        Tuple of (result_text, perspectives_succeeded, perspectives_total, success)
    """
    if perspectives is None:
        perspectives = ["security", "performance", "architecture"]
    
    valid_perspectives = [p for p in perspectives if p in PERSPECTIVE_PROMPTS]
    if not valid_perspectives:
        return (
            "ERROR: No valid perspectives specified. Valid options: " + ", ".join(PERSPECTIVE_PROMPTS.keys()),
            0,
            len(perspectives),
            False,
        )
    
    logger.info(f"[Analyzer] Starting parallel analysis with perspectives: {valid_perspectives}")
    
    should_close = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=120.0)
        should_close = True
    
    try:
        await _ensure_findings_dir(chat_id, http_client)
        
        full_context = context
        if target_paths:
            full_context += "\n\nTarget paths to focus on:\n" + "\n".join(f"- {p}" for p in target_paths)
        
        tasks = []
        for p in valid_perspectives:
            prompt = render_template(f"analyzer_{p}.j2", context=full_context)
            output_file = f"findings/{p}.md"
            
            tasks.append(
                run_subagent(
                    system_prompt=prompt,
                    user_message=f"Analyze from {p} perspective. Write to /home/user/workspace/{output_file}.",
                    chat_id=chat_id,
                    model=resolve_preset_to_model(ORCHESTRATOR_ANALYSIS_MODEL),
                    preset_hint=ORCHESTRATOR_ANALYSIS_MODEL,
                    max_turns=ORCHESTRATOR_ANALYSIS_MAX_TURNS,
                    http_client=http_client,
                )
            )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        succeeded = 0
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"[Analyzer] Perspective {valid_perspectives[i]} failed: {r}")
            elif isinstance(r, StepResult) and r.success:
                succeeded += 1
                logger.info(f"[Analyzer] Perspective {valid_perspectives[i]} completed")
            else:
                error = r.error if isinstance(r, StepResult) else "Unknown error"
                logger.warning(f"[Analyzer] Perspective {valid_perspectives[i]} failed: {error}")
        
        logger.info("[Analyzer] Running synthesizer...")
        synth_result = await run_subagent(
            system_prompt=load_prompt("synthesizer.j2"),
            user_message="Synthesize all analysis findings from /home/user/workspace/findings/.",
            chat_id=chat_id,
            model=resolve_preset_to_model(ORCHESTRATOR_SYNTHESIS_MODEL),
            preset_hint=ORCHESTRATOR_SYNTHESIS_MODEL,
            max_turns=10,
            http_client=http_client,
        )
        
        lines = [
            f"Parallel analysis complete. {succeeded}/{len(valid_perspectives)} perspectives succeeded.",
            f"Synthesized report: /home/user/workspace/findings/synthesized.md",
        ]
        
        if synth_result.success:
            lines.append("Read the synthesized report for prioritized findings and action plan.")
        else:
            lines.append(f"Synthesis failed: {synth_result.error}. Read individual findings/ files.")
        
        return "\n".join(lines), succeeded, len(valid_perspectives), True
        
    except Exception as e:
        logger.error(f"[Analyzer] Parallel analysis error: {e}")
        return f"Parallel analysis failed: {type(e).__name__}: {e}", 0, len(valid_perspectives), False
    finally:
        if should_close:
            await http_client.aclose()


async def _ensure_findings_dir(chat_id: str, http_client: httpx.AsyncClient) -> None:
    """Ensure the findings directory exists."""
    from pathlib import Path
    try:
        workdir = Path(get_local_sandbox().get_working_dir(chat_id))
        findings_dir = workdir / "findings"
        findings_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[Analyzer] Failed to create findings dir: {e}")


# =============================================================================
# Legacy async function for backwards compatibility
# =============================================================================

async def analyze_parallel(
    context: str,
    target_paths: Optional[List[str]] = None,
    perspectives: Optional[List[str]] = None,
    *,
    chat_id: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Run parallel analysis from multiple perspectives.
    
    This function is kept for backwards compatibility.
    """
    result, _, _, _ = await _analyze_parallel_impl(
        context=context,
        target_paths=target_paths or [],
        perspectives=perspectives or ["security", "performance", "architecture"],
        chat_id=chat_id,
        http_client=http_client,
    )
    return result


# =============================================================================
# Tool Registration Helper
# =============================================================================

def get_analyzer_tools(
    chat_id: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[Tool]:
    """Get analyzer tool specifications for Agent initialization.
    
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
        Tool(name="analyze_parallel", params={"chat_id": chat_id}),
    ]


# Schema export for backwards compatibility
ANALYZE_PARALLEL_SCHEMA = {
    "name": "analyze_parallel",
    "description": ANALYZE_PARALLEL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "context": {
                "type": "string",
                "description": "What to analyze and any specific concerns."
            },
            "target_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Workspace paths to focus on. Subagents can also explore freely."
            },
            "perspectives": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Which perspectives. Default: ['security', 'performance', 'architecture']."
            }
        },
        "required": ["context"]
    }
}
