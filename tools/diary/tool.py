"""Diary tool plugin -- write-only diary entries and mental health signal computation.

Exports:
    get_tools()       -> SDK Tool objects (side effect: register_tool() calls)
    get_schemas()     -> snake_case name -> JSON schema
    execute(name, args) -> async dispatcher for non-agentic path
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Sequence

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

class WriteDiaryEntryAction(Action):
    content: str = Field(description="Raw journal/rant text to write")
    user_pk: str = Field(default="operator", description="User partition key")

class WriteDiaryEntryObservation(Observation):
    pass

class WriteDiaryEntryExecutor(ToolExecutor[WriteDiaryEntryAction, WriteDiaryEntryObservation]):
    def __call__(self, action: WriteDiaryEntryAction, conversation=None) -> WriteDiaryEntryObservation:
        from diary import write_diary_entry
        result = _run_async(write_diary_entry(action.content, action.user_pk))
        return WriteDiaryEntryObservation.from_text(_format_result(result))

class WriteDiaryEntryTool(ToolDefinition[WriteDiaryEntryAction, WriteDiaryEntryObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["WriteDiaryEntryTool"]:
        return [cls(
            description=(
                "Write a diary entry. Use when the user wants to vent, journal, or record thoughts. "
                "Entries are private (never shown back to user) and auto-expire after 3 days."
            ),
            action_type=WriteDiaryEntryAction,
            observation_type=WriteDiaryEntryObservation,
            executor=WriteDiaryEntryExecutor(),
        )]

class ComputeDiarySignalAction(Action):
    user_pk: str = Field(default="operator", description="User partition key")

class ComputeDiarySignalObservation(Observation):
    pass

class ComputeDiarySignalExecutor(ToolExecutor[ComputeDiarySignalAction, ComputeDiarySignalObservation]):
    def __call__(self, action: ComputeDiarySignalAction, conversation=None) -> ComputeDiarySignalObservation:
        from diary import compute_diary_signal
        result = _run_async(compute_diary_signal(action.user_pk))
        return ComputeDiarySignalObservation.from_text(_format_result(result))

class ComputeDiarySignalTool(ToolDefinition[ComputeDiarySignalAction, ComputeDiarySignalObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["ComputeDiarySignalTool"]:
        return [cls(
            description=(
                "Compute a mental health signal from recent diary entries. "
                "Returns a score (0-10), trend, themes, life_load, and social_battery. "
                "Use when asked about overall mental state or to trigger signal update."
            ),
            action_type=ComputeDiarySignalAction,
            observation_type=ComputeDiarySignalObservation,
            executor=ComputeDiarySignalExecutor(),
        )]

register_tool("WriteDiaryEntryTool", WriteDiaryEntryTool)
register_tool("ComputeDiarySignalTool", ComputeDiarySignalTool)

def get_tools() -> List[Tool]:
    """Get all diary SDK Tool objects (side effect: register_tool already called above)."""
    return [
        Tool(name="WriteDiaryEntryTool"),
        Tool(name="ComputeDiarySignalTool"),
    ]

def get_schemas() -> Dict[str, Dict[str, Any]]:
    """Return snake_case tool name -> JSON schema mapping."""
    return {
        "write_diary_entry": {
            "name": "write_diary_entry",
            "description": (
                "Write a diary entry. Entries are private (never shown back to user) "
                "and auto-expire after 3 days."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Raw journal/rant text to write",
                    },
                    "user_pk": {
                        "type": "string",
                        "description": "User partition key",
                        "default": "operator",
                    },
                },
                "required": ["content"],
            },
        },
        "compute_diary_signal": {
            "name": "compute_diary_signal",
            "description": (
                "Compute a mental health signal from recent diary entries. "
                "Returns a score (0-10), trend, themes, life_load, and social_battery."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_pk": {
                        "type": "string",
                        "description": "User partition key",
                        "default": "operator",
                    },
                },
                "required": [],
            },
        },
    }

async def execute(name: str, args: Dict[str, Any]) -> str:
    """Route diary tool calls to the underlying diary module functions."""
    from diary import write_diary_entry, compute_diary_signal

    ROUTES = {
        "write_diary_entry": lambda: write_diary_entry(
            args["content"], args.get("user_pk", "operator")
        ),
        "compute_diary_signal": lambda: compute_diary_signal(
            args.get("user_pk", "operator")
        ),
    }

    handler = ROUTES.get(name)
    if not handler:
        return f"Unknown diary tool: {name}"

    result = handler()
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)
