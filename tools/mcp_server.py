"""MCP server wrapper for IF tool plugins."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("if_mcp_server")

TOOL_CATEGORIES = {
    "health": ["health"],
    "finance": ["finance"],
    "diary": ["diary"],
    "proposals": ["proposals"],
    "supplement_research": ["supplement_research"],
    "temporal": [
        "temporal_age",
        "temporal_city_time",
        "temporal_duration",
        "temporal_from_unix",
        "temporal_resolve",
        "temporal_timezone",
        "temporal_to_unix",
    ],
    "tarot": ["tarot"],
}

class Plugin:
    def __init__(self, slug: str, path: Path, module: Any, schemas: dict[str, dict[str, Any]]):
        self.slug = slug
        self.path = path
        self.module = module
        self.schemas = schemas

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent

def _tools_root() -> Path:
    return Path(os.environ.get("IF_TOOLS_ROOT") or Path(__file__).resolve().parent)

def _category_slugs(category: str) -> list[str]:
    slugs = TOOL_CATEGORIES.get(category)
    if slugs:
        return slugs

    plugin_dir = _tools_root() / category
    if (plugin_dir / "tool.py").exists():
        return [category]

    raise ValueError(f"Unknown tool category: {category}")

def _allowed_tools() -> set[str]:
    raw = os.environ.get("IF_MCP_ALLOWED_TOOLS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}

def _app_src() -> Path:
    root = _repo_root()
    if (root / "app" / "src").exists():
        return root / "app" / "src"
    if (root / "src").exists():
        return root / "src"
    return root / "app" / "src"

def _schema_from_tool_meta(path: Path) -> dict[str, dict[str, Any]]:
    meta_path = path / "tool_meta.yaml"
    if not meta_path.exists():
        return {}
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    schemas: dict[str, dict[str, Any]] = {}
    for name, schema in (data.get("tools") or {}).items():
        schemas[name] = {
            "name": name,
            "description": schema.get("description", name),
            "parameters": schema.get("parameters") or {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
    return schemas

def _load_plugin(slug: str) -> Plugin:
    tools_root = _tools_root()
    plugin_dir = tools_root / slug
    tool_path = plugin_dir / "tool.py"
    if not tool_path.exists():
        raise FileNotFoundError(f"Plugin tool.py not found: {tool_path}")

    for path in (str(_repo_root()), str(_app_src()), str(plugin_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)

    module_name = f"if_mcp_tool_{slug}"
    spec = importlib.util.spec_from_file_location(module_name, tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import plugin: {slug}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if hasattr(module, "get_schemas"):
        schemas = module.get_schemas()
    else:
        schemas = _schema_from_tool_meta(plugin_dir)
    return Plugin(slug=slug, path=plugin_dir, module=module, schemas=schemas)

def _normalize_schema(schema: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    parameters = schema.get("parameters") or schema.get("inputSchema") or {
        "type": "object",
        "properties": {},
        "required": [],
    }
    return {
        "name": schema.get("name") or fallback_name,
        "description": schema.get("description") or fallback_name,
        "inputSchema": parameters,
    }

def _build_server(category: str) -> tuple[Any, dict[str, Plugin], list[dict[str, Any]]]:
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError as exc:
        raise RuntimeError("Python package 'mcp' is required to run IF MCP servers") from exc

    slugs = _category_slugs(category)
    allowed = _allowed_tools()

    plugins = [_load_plugin(slug) for slug in slugs]
    tool_to_plugin: dict[str, Plugin] = {}
    normalized_tools: list[dict[str, Any]] = []
    for plugin in plugins:
        for name, schema in plugin.schemas.items():
            normalized = _normalize_schema(schema, name)
            if allowed and normalized["name"] not in allowed:
                continue
            normalized_tools.append(normalized)
            tool_to_plugin[normalized["name"]] = plugin

    server = Server(f"if-{category}")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"],
            )
            for tool in normalized_tools
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[TextContent]:
        plugin = tool_to_plugin.get(name)
        if plugin is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        result = await plugin.module.execute(name, arguments or {})
        if not isinstance(result, str):
            result = json.dumps(result, indent=2, default=str)
        return [TextContent(type="text", text=result)]

    return server, tool_to_plugin, normalized_tools


async def _run_stdio(server: Any) -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _run_http(server: Any, host: str, port: int, mount_path: str) -> None:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: Any) -> Any:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[Mount(mount_path, app=session_manager.handle_request)],
        lifespan=lifespan,
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level=os.environ.get("IF_MCP_LOG_LEVEL", "info"),
        access_log=False,
    )
    http_server = uvicorn.Server(config)
    logger.info("MCP HTTP server listening on %s:%s%s", host, port, mount_path)
    await http_server.serve()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mcp_server",
        description="Run an IF MCP tool category over stdio or streamable HTTP.",
    )
    parser.add_argument("category", help="Tool category (e.g. health, finance, tarot, temporal_age).")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.environ.get("IF_MCP_TRANSPORT", "stdio"),
        help="Transport to expose. Default stdio. Per-category MCP pods use http.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("IF_MCP_HOST", "0.0.0.0"),
        help="HTTP bind host (only used with --transport http).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("IF_MCP_PORT", "8000")),
        help="HTTP bind port (only used with --transport http).",
    )
    parser.add_argument(
        "--mount-path",
        default=os.environ.get("IF_MCP_MOUNT_PATH", "/mcp"),
        help="Path the HTTP handler is mounted at (default /mcp).",
    )
    return parser.parse_args(argv)


async def main() -> None:
    args = _parse_args(sys.argv[1:])
    server, _tool_to_plugin, _tools = _build_server(args.category)
    if args.transport == "http":
        await _run_http(server, args.host, args.port, args.mount_path)
    else:
        await _run_stdio(server)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("IF_MCP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(main())
