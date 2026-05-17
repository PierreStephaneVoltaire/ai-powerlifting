"""App-side MCP subprocess manager and tool dispatcher."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import EXTERNAL_TOOLS_PATH, EXTERNAL_TOOLS_FALLBACK, MCP_SERVER_CATEGORIES

logger = logging.getLogger(__name__)

_manager: Optional["MCPToolManager"] = None


@dataclass
class ManagedServer:
    category: str
    session: Any = None
    client_cm: Any = None
    session_cm: Any = None
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _tool_to_openai_schema(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description") or tool["name"],
            "parameters": tool.get("inputSchema") or tool.get("parameters") or {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }


def _text_from_mcp_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if content is None:
        return json.dumps(result, default=str)
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        if text is not None:
            parts.append(str(text))
    return "\n".join(parts)


def _builtin_tools() -> dict[str, dict[str, Any]]:
    return {
        "get_current_date": {
            "name": "get_current_date",
            "description": "Return the current local date/time and UTC date/time.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
            "_category": "__builtin__",
        }
    }


class MCPToolManager:
    def __init__(
        self,
        categories: list[str] | None = None,
        tools_root: str | Path | None = None,
    ):
        self.categories = categories or list(MCP_SERVER_CATEGORIES)
        self.tools_root = Path(tools_root or EXTERNAL_TOOLS_PATH or EXTERNAL_TOOLS_FALLBACK)
        self._servers: dict[str, ManagedServer] = {}
        self._tool_index: dict[str, tuple[str, dict[str, Any]]] = {}
        for name, schema in _builtin_tools().items():
            self._tool_index[name] = ("__builtin__", schema)

    async def start_all(self) -> None:
        for category in self.categories:
            try:
                await self.start(category)
            except Exception as exc:
                logger.warning("MCP server %s failed to start: %s", category, exc)

    async def start(self, category: str) -> None:
        if category in self._servers:
            return
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise RuntimeError("Python package 'mcp' is required for MCP tool servers") from exc

        server_script = self.tools_root / "mcp_server.py"
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(server_script), category],
            env={**os.environ, "IF_TOOLS_ROOT": str(self.tools_root)},
        )
        client_cm = stdio_client(params)
        read_stream, write_stream = await client_cm.__aenter__()
        session_cm = ClientSession(read_stream, write_stream)
        session = await session_cm.__aenter__()
        await session.initialize()
        tools_result = await session.list_tools()
        managed = ManagedServer(
            category=category,
            session=session,
            client_cm=client_cm,
            session_cm=session_cm,
        )

        for tool in getattr(tools_result, "tools", []):
            schema = {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
                "_category": category,
            }
            managed.tools[tool.name] = schema
            self._tool_index[tool.name] = (category, schema)

        self._servers[category] = managed
        logger.info("MCP server %s started with %s tools", category, len(managed.tools))

    async def stop(self, category: str) -> None:
        managed = self._servers.pop(category, None)
        if not managed:
            return
        for name in list(managed.tools.keys()):
            self._tool_index.pop(name, None)
        if managed.session_cm:
            try:
                await managed.session_cm.__aexit__(None, None, None)
            except BaseException as exc:
                logger.debug("MCP session close failed for %s: %s", category, exc)
        if managed.client_cm:
            try:
                await managed.client_cm.__aexit__(None, None, None)
            except BaseException as exc:
                logger.debug("MCP client close failed for %s: %s", category, exc)
        logger.info("MCP server %s stopped", category)

    async def stop_all(self) -> None:
        for category in list(self._servers.keys()):
            try:
                await self.stop(category)
            except BaseException as exc:
                logger.debug("MCP stop failed for %s: %s", category, exc)

    async def reload(self, category: str | None = None) -> dict[str, str]:
        targets = [category] if category else list(self.categories)
        statuses: dict[str, str] = {}
        for target in targets:
            if target not in self.categories:
                statuses[target] = "failed: unknown category"
                continue
            try:
                await self.stop(target)
                await self.start(target)
                statuses[target] = "reloaded"
            except Exception as exc:
                logger.exception("MCP reload failed for %s", target)
                statuses[target] = f"failed: {exc}"
        return statuses

    def list_tool_names(self) -> list[str]:
        return sorted(self._tool_index)

    def has_tool(self, name: str) -> bool:
        return name in self._tool_index

    def tools_for_names(self, names: list[str] | set[str]) -> list[dict[str, Any]]:
        wanted = set(names)
        return [
            _tool_to_openai_schema(schema)
            for tool_name, (_, schema) in sorted(self._tool_index.items())
            if tool_name in wanted
        ]

    def all_openai_tools(self) -> list[dict[str, Any]]:
        return [
            _tool_to_openai_schema(schema)
            for _, schema in sorted(self._tool_index.values(), key=lambda item: item[1]["name"])
        ]

    async def call_tool(self, name: str, args: dict[str, Any] | None = None) -> str:
        args = dict(args or {})
        entry = self._tool_index.get(name)
        if not entry:
            raise KeyError(f"Unknown tool: {name}")
        category, _schema = entry
        if category == "__builtin__":
            if name == "get_current_date":
                return json.dumps(
                    {
                        "local": datetime.now().astimezone().isoformat(),
                        "utc": datetime.utcnow().isoformat() + "Z",
                    },
                    indent=2,
                )
            raise KeyError(f"Unknown builtin tool: {name}")

        if category not in self._servers:
            await self.start(category)
        managed = self._servers[category]
        async with managed.lock:
            result = await managed.session.call_tool(name, args)
        return _text_from_mcp_result(result)


def init_mcp_manager() -> MCPToolManager:
    global _manager
    _manager = MCPToolManager()
    return _manager


def get_mcp_manager() -> MCPToolManager:
    global _manager
    if _manager is None:
        _manager = MCPToolManager()
    return _manager


async def shutdown_mcp_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.stop_all()
        _manager = None
