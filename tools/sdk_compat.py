"""Small compatibility types for legacy SDK-style tool adapters.

The MCP migration no longer depends on OpenHands. Some plugin files still
contain legacy SDK adapter classes next to the real `get_schemas()` and
`execute()` business logic, so these no-op types keep those modules importable
without pulling in the OpenHands SDK.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class Action(BaseModel):
    class Config:
        arbitrary_types_allowed = True


@dataclass
class TextContent:
    text: str


class Observation(BaseModel):
    content: list[Any] = []

    @classmethod
    def from_text(cls, text: str):
        return cls(content=[TextContent(text=text)])


class Tool(BaseModel):
    name: str


class ToolExecutor:
    def __class_getitem__(cls, _item):
        return cls


class ToolDefinition:
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, **kwargs: Any):
        for key, value in kwargs.items():
            setattr(self, key, value)


def register_tool(_name: str, _tool: Any) -> None:
    return None

