"""CLI bridge so opencode can call IF MCP tools from shell."""
from __future__ import annotations

import asyncio
import json
import sys

from mcp_runtime.manager import MCPToolManager


async def _main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m mcp_runtime.invoke_tool <tool_name> [json_args]", file=sys.stderr)
        return 2

    tool_name = sys.argv[1]
    raw_args = sys.argv[2] if len(sys.argv) > 2 else "{}"
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON args: {exc}", file=sys.stderr)
        return 2
    if not isinstance(args, dict):
        print("Tool args must be a JSON object", file=sys.stderr)
        return 2

    manager = MCPToolManager()
    if tool_name != "get_current_date":
        await manager.start_all()
    try:
        result = await manager.call_tool(tool_name, args)
        print(result)
    finally:
        await manager.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
