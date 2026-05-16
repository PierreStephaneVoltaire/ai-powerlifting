"""Proposal tool plugin — agent-proposed directives and implementation proposals.

Provides tools for:
- create_proposal(): Agent creates a proposal (capped at 3 per summarization)
- list_proposals(): Query proposals with optional status filter
- resolve_proposal(): User approves/rejects a proposal
- generate_implementation_plan(): Generate step-by-step plan for approved proposals

Design principle: Agent proposes, user approves.

Exports:
    get_tools()       -> SDK Tool objects (side effect: register_tool() calls)
    get_schemas()     -> snake_case name -> JSON schema
    execute(name, args) -> async dispatcher for non-agentic path
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import Field

from tools.sdk_compat import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


# =============================================================================
# Helpers (duplicated from agent/tools/base to avoid cross-dir imports)
# =============================================================================

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


def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)


# =============================================================================
# Type aliases
# =============================================================================

ProposalType = Literal[
    "new_directive",
    "rewrite_directive",
    "deprecate_directive",
    "new_tool",
    "system_observation",
]

ProposalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "implemented",
]


# =============================================================================
# SDK Tool Classes
# =============================================================================

# --- create_proposal ---

class CreateProposalAction(Action):
    type: ProposalType = Field(description="Type: new_directive, rewrite_directive, deprecate_directive, new_tool, system_observation")
    title: str = Field(description="Short title for the proposal")
    rationale: str = Field(description="Why this proposal is needed")
    content: str = Field(description="Full proposal content (directive text, tool spec, etc.)")
    target_id: Optional[str] = Field(default=None, description="For rewrite/deprecate, the SK of target directive")
    user_pk: str = Field(default="operator", description="User partition key")


class CreateProposalObservation(Observation):
    pass


class CreateProposalExecutor(ToolExecutor[CreateProposalAction, CreateProposalObservation]):
    def __call__(self, action: CreateProposalAction, conversation=None) -> CreateProposalObservation:
        from agent.tools.proposal_tools import create_proposal
        result = _run_async(create_proposal(
            type=action.type,
            title=action.title,
            rationale=action.rationale,
            content=action.content,
            target_id=action.target_id,
            user_pk=action.user_pk,
        ))
        return CreateProposalObservation.from_text(_format_result(result))


class CreateProposalTool(ToolDefinition[CreateProposalAction, CreateProposalObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["CreateProposalTool"]:
        return [cls(
            description=(
                "Create a proposal for a new directive, tool, or system change. "
                "Proposals require user approval before implementation. "
                "Capped at 3 proposals per summarization run."
            ),
            action_type=CreateProposalAction,
            observation_type=CreateProposalObservation,
            executor=CreateProposalExecutor(),
        )]


# --- list_proposals ---

class ListProposalsAction(Action):
    status: Optional[ProposalStatus] = Field(default=None, description="Filter by status: pending, approved, rejected, implemented")
    user_pk: str = Field(default="operator", description="User partition key")
    limit: int = Field(default=20, description="Maximum number of proposals to return")


class ListProposalsObservation(Observation):
    pass


class ListProposalsExecutor(ToolExecutor[ListProposalsAction, ListProposalsObservation]):
    def __call__(self, action: ListProposalsAction, conversation=None) -> ListProposalsObservation:
        from agent.tools.proposal_tools import list_proposals
        result = _run_async(list_proposals(
            status=action.status,
            user_pk=action.user_pk,
            limit=action.limit,
        ))
        return ListProposalsObservation.from_text(_format_result(result))


class ListProposalsTool(ToolDefinition[ListProposalsAction, ListProposalsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ListProposalsTool"]:
        return [cls(
            description=(
                "List proposals, optionally filtered by status. "
                "Use to show pending proposals for user review."
            ),
            action_type=ListProposalsAction,
            observation_type=ListProposalsObservation,
            executor=ListProposalsExecutor(),
        )]


# --- resolve_proposal ---

class ResolveProposalAction(Action):
    sk: str = Field(description="Sort key of the proposal (e.g., proposal#2026-03-14T10:00:00Z)")
    decision: Literal["approved", "rejected"] = Field(description="Decision: approved or rejected")
    reason: Optional[str] = Field(default=None, description="Reason for rejection (required if rejected)")
    user_pk: str = Field(default="operator", description="User partition key")


class ResolveProposalObservation(Observation):
    pass


class ResolveProposalExecutor(ToolExecutor[ResolveProposalAction, ResolveProposalObservation]):
    def __call__(self, action: ResolveProposalAction, conversation=None) -> ResolveProposalObservation:
        from agent.tools.proposal_tools import resolve_proposal
        result = _run_async(resolve_proposal(
            sk=action.sk,
            decision=action.decision,
            reason=action.reason,
            user_pk=action.user_pk,
        ))
        return ResolveProposalObservation.from_text(_format_result(result))


class ResolveProposalTool(ToolDefinition[ResolveProposalAction, ResolveProposalObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ResolveProposalTool"]:
        return [cls(
            description=(
                "Resolve a proposal by approving or rejecting it. "
                "If approved, an implementation plan will be automatically generated."
            ),
            action_type=ResolveProposalAction,
            observation_type=ResolveProposalObservation,
            executor=ResolveProposalExecutor(),
        )]


# --- generate_implementation_plan ---

class GenerateImplementationPlanAction(Action):
    proposal_sk: str = Field(description="Sort key of the approved proposal")
    user_pk: str = Field(default="operator", description="User partition key")


class GenerateImplementationPlanObservation(Observation):
    pass


class GenerateImplementationPlanExecutor(ToolExecutor[GenerateImplementationPlanAction, GenerateImplementationPlanObservation]):
    def __call__(self, action: GenerateImplementationPlanAction, conversation=None) -> GenerateImplementationPlanObservation:
        from agent.tools.proposal_tools import generate_implementation_plan
        result = _run_async(generate_implementation_plan(
            proposal_sk=action.proposal_sk,
            user_pk=action.user_pk,
        ))
        return GenerateImplementationPlanObservation.from_text(_format_result(result))


class GenerateImplementationPlanTool(ToolDefinition[GenerateImplementationPlanAction, GenerateImplementationPlanObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["GenerateImplementationPlanTool"]:
        return [cls(
            description=(
                "Generate an implementation plan for an approved proposal. "
                "Usually called automatically after approval, but can be called manually."
            ),
            action_type=GenerateImplementationPlanAction,
            observation_type=GenerateImplementationPlanObservation,
            executor=GenerateImplementationPlanExecutor(),
        )]


# =============================================================================
# Register all SDK tools
# =============================================================================

register_tool("CreateProposalTool", CreateProposalTool)
register_tool("ListProposalsTool", ListProposalsTool)
register_tool("ResolveProposalTool", ResolveProposalTool)
register_tool("GenerateImplementationPlanTool", GenerateImplementationPlanTool)


# =============================================================================
# Plugin contract: get_tools()
# =============================================================================

def get_tools() -> List[Tool]:
    """Get all proposal SDK Tool objects (side effect: register_tool already called above)."""
    return [
        Tool(name="CreateProposalTool"),
        Tool(name="ListProposalsTool"),
        Tool(name="ResolveProposalTool"),
        Tool(name="GenerateImplementationPlanTool"),
    ]


# =============================================================================
# Plugin contract: get_schemas() -- JSON schemas for non-agentic specialist path
# =============================================================================

def get_schemas() -> Dict[str, Dict[str, Any]]:
    """Return snake_case tool name -> JSON schema mapping."""
    return {
        "create_proposal": {
            "name": "create_proposal",
            "description": (
                "Create a proposal for a new directive, tool, or system change. "
                "Proposals require user approval before implementation. "
                "Capped at 3 proposals per summarization run."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["new_directive", "rewrite_directive", "deprecate_directive", "new_tool", "system_observation"],
                        "description": "Type: new_directive, rewrite_directive, deprecate_directive, new_tool, system_observation",
                    },
                    "title": {"type": "string", "description": "Short title for the proposal"},
                    "rationale": {"type": "string", "description": "Why this proposal is needed"},
                    "content": {"type": "string", "description": "Full proposal content (directive text, tool spec, etc.)"},
                    "target_id": {"type": "string", "description": "For rewrite/deprecate, the SK of target directive"},
                    "user_pk": {"type": "string", "description": "User partition key", "default": "operator"},
                },
                "required": ["type", "title", "rationale", "content"],
            },
        },
        "list_proposals": {
            "name": "list_proposals",
            "description": (
                "List proposals, optionally filtered by status. "
                "Use to show pending proposals for user review."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "approved", "rejected", "implemented"],
                        "description": "Filter by status: pending, approved, rejected, implemented",
                    },
                    "user_pk": {"type": "string", "description": "User partition key", "default": "operator"},
                    "limit": {"type": "integer", "description": "Maximum number of proposals to return", "default": 20},
                },
                "required": [],
            },
        },
        "resolve_proposal": {
            "name": "resolve_proposal",
            "description": (
                "Resolve a proposal by approving or rejecting it. "
                "If approved, an implementation plan will be automatically generated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sk": {"type": "string", "description": "Sort key of the proposal (e.g., proposal#2026-03-14T10:00:00Z)"},
                    "decision": {
                        "type": "string",
                        "enum": ["approved", "rejected"],
                        "description": "Decision: approved or rejected",
                    },
                    "reason": {"type": "string", "description": "Reason for rejection (required if rejected)"},
                    "user_pk": {"type": "string", "description": "User partition key", "default": "operator"},
                },
                "required": ["sk", "decision"],
            },
        },
        "generate_implementation_plan": {
            "name": "generate_implementation_plan",
            "description": (
                "Generate an implementation plan for an approved proposal. "
                "Usually called automatically after approval, but can be called manually."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_sk": {"type": "string", "description": "Sort key of the approved proposal"},
                    "user_pk": {"type": "string", "description": "User partition key", "default": "operator"},
                },
                "required": ["proposal_sk"],
            },
        },
    }


# =============================================================================
# Plugin contract: execute() -- async dispatcher for non-agentic specialist path
# =============================================================================

async def execute(name: str, args: Dict[str, Any]) -> str:
    """Route proposal tool calls to the underlying proposal module functions."""
    from agent.tools.proposal_tools import (
        create_proposal,
        list_proposals,
        resolve_proposal,
        generate_implementation_plan,
    )

    ROUTES = {
        "create_proposal": lambda: create_proposal(
            type=args["type"],
            title=args["title"],
            rationale=args["rationale"],
            content=args["content"],
            target_id=args.get("target_id"),
            user_pk=args.get("user_pk", "operator"),
        ),
        "list_proposals": lambda: list_proposals(
            status=args.get("status"),
            user_pk=args.get("user_pk", "operator"),
            limit=args.get("limit", 20),
        ),
        "resolve_proposal": lambda: resolve_proposal(
            sk=args["sk"],
            decision=args["decision"],
            reason=args.get("reason"),
            user_pk=args.get("user_pk", "operator"),
        ),
        "generate_implementation_plan": lambda: generate_implementation_plan(
            proposal_sk=args["proposal_sk"],
            user_pk=args.get("user_pk", "operator"),
        ),
    }

    handler = ROUTES.get(name)
    if not handler:
        return f"Unknown proposal tool: {name}"

    result = await handler()
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)
