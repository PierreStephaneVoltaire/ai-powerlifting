
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

def _proposal_table():
    import boto3
    from config import AWS_REGION, IF_PROPOSALS_TABLE_NAME

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(IF_PROPOSALS_TABLE_NAME)

async def create_proposal(
    *,
    type: str,
    title: str,
    rationale: str,
    content: str,
    target_id: Optional[str] = None,
    user_pk: str = "operator",
) -> Dict[str, Any]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "pk": user_pk,
        "sk": f"proposal#{now}",
        "type": type,
        "title": title,
        "rationale": rationale,
        "content": content,
        "target_id": target_id,
        "status": "pending",
        "author": "agent",
        "created_at": now,
        "updated_at": now,
    }
    _proposal_table().put_item(Item=item)
    return {"proposal": item}

async def list_proposals(
    status: Optional[str] = None,
    user_pk: str = "operator",
    limit: int = 20,
) -> Dict[str, Any]:
    from boto3.dynamodb.conditions import Key

    response = _proposal_table().query(
        KeyConditionExpression=Key("pk").eq(user_pk) & Key("sk").begins_with("proposal#"),
        Limit=max(1, min(int(limit), 100)),
        ScanIndexForward=False,
    )
    proposals = response.get("Items", [])
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"proposals": proposals}

async def resolve_proposal(
    *,
    sk: str,
    decision: str,
    reason: Optional[str] = None,
    user_pk: str = "operator",
) -> Dict[str, Any]:
    from datetime import datetime, timezone

    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    now = datetime.now(timezone.utc).isoformat()
    table = _proposal_table()
    response = table.update_item(
        Key={"pk": user_pk, "sk": sk},
        UpdateExpression="SET #status=:status, updated_at=:updated_at, decision_reason=:reason",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": decision,
            ":updated_at": now,
            ":reason": reason or "",
        },
        ReturnValues="ALL_NEW",
    )
    return {"proposal": response.get("Attributes", {})}

async def generate_implementation_plan(
    *,
    proposal_sk: str,
    user_pk: str = "operator",
) -> Dict[str, Any]:
    response = _proposal_table().get_item(Key={"pk": user_pk, "sk": proposal_sk})
    proposal = response.get("Item")
    if not proposal:
        return {"error": f"Proposal not found: {proposal_sk}"}
    plan = [
        "Confirm the proposal is still desired and scoped.",
        "Identify affected directives, prompts, tools, or docs.",
        "Make the smallest coherent change.",
        "Run focused verification.",
        "Mark the proposal implemented when merged/deployed.",
    ]
    return {"proposal_sk": proposal_sk, "title": proposal.get("title"), "implementation_plan": plan}

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

class ListProposalsAction(Action):
    status: Optional[ProposalStatus] = Field(default=None, description="Filter by status: pending, approved, rejected, implemented")
    user_pk: str = Field(default="operator", description="User partition key")
    limit: int = Field(default=20, description="Maximum number of proposals to return")

class ListProposalsObservation(Observation):
    pass

class ListProposalsExecutor(ToolExecutor[ListProposalsAction, ListProposalsObservation]):
    def __call__(self, action: ListProposalsAction, conversation=None) -> ListProposalsObservation:
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

class ResolveProposalAction(Action):
    sk: str = Field(description="Sort key of the proposal (e.g., proposal#2026-03-14T10:00:00Z)")
    decision: Literal["approved", "rejected"] = Field(description="Decision: approved or rejected")
    reason: Optional[str] = Field(default=None, description="Reason for rejection (required if rejected)")
    user_pk: str = Field(default="operator", description="User partition key")

class ResolveProposalObservation(Observation):
    pass

class ResolveProposalExecutor(ToolExecutor[ResolveProposalAction, ResolveProposalObservation]):
    def __call__(self, action: ResolveProposalAction, conversation=None) -> ResolveProposalObservation:
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

class GenerateImplementationPlanAction(Action):
    proposal_sk: str = Field(description="Sort key of the approved proposal")
    user_pk: str = Field(default="operator", description="User partition key")

class GenerateImplementationPlanObservation(Observation):
    pass

class GenerateImplementationPlanExecutor(ToolExecutor[GenerateImplementationPlanAction, GenerateImplementationPlanObservation]):
    def __call__(self, action: GenerateImplementationPlanAction, conversation=None) -> GenerateImplementationPlanObservation:
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

register_tool("CreateProposalTool", CreateProposalTool)
register_tool("ListProposalsTool", ListProposalsTool)
register_tool("ResolveProposalTool", ResolveProposalTool)
register_tool("GenerateImplementationPlanTool", GenerateImplementationPlanTool)

def get_tools() -> List[Tool]:
    """Get all proposal SDK Tool objects (side effect: register_tool already called above)."""
    return [
        Tool(name="CreateProposalTool"),
        Tool(name="ListProposalsTool"),
        Tool(name="ResolveProposalTool"),
        Tool(name="GenerateImplementationPlanTool"),
    ]

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

async def execute(name: str, args: Dict[str, Any]) -> str:
    """Route proposal tool calls to the underlying proposal module functions."""
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
