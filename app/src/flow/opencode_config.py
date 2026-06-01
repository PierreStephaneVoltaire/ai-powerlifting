"""Per-run OpenCode MCP configuration for IF specialists."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from config import APP_SRC, EXTERNAL_TOOLS_FALLBACK, EXTERNAL_TOOLS_PATH, PROJECT_ROOT
from mcp_runtime import get_mcp_manager

logger = logging.getLogger(__name__)


def _pythonpath() -> str:
    return os.pathsep.join([str(APP_SRC), str(PROJECT_ROOT)])


def _tools_root() -> Path:
    return Path(EXTERNAL_TOOLS_PATH or EXTERNAL_TOOLS_FALLBACK)


def _if_mcp_server(category: str, allowed_tools: list[str]) -> dict[str, Any]:
    tools_root = _tools_root()
    return {
        "type": "local",
        "command": [sys.executable, str(tools_root / "mcp_server.py"), category],
        "environment": {
            "IF_TOOLS_ROOT": str(tools_root),
            "IF_MCP_ALLOWED_TOOLS": ",".join(sorted(set(allowed_tools))),
            "IF_DISABLE_POWERLIFTING_DATASET_SYNC": "1",
            "PYTHONPATH": _pythonpath(),
        },
        "enabled": True,
        "timeout": 60000,
    }


def _external_mcp_servers(server_names: set[str]) -> dict[str, dict[str, Any]]:
    if not server_names:
        return {}
    try:
        from mcp_servers.config import get_available_servers
    except Exception as exc:
        logger.warning("External MCP server config unavailable: %s", exc)
        return {}

    configured = get_available_servers()
    result: dict[str, dict[str, Any]] = {}
    for name in sorted(server_names):
        server = configured.get(name)
        if not server:
            logger.warning("Specialist referenced unknown external MCP server: %s", name)
            continue
        command = [str(server.get("command") or "")]
        command.extend(str(arg) for arg in server.get("args") or [])
        if not command[0]:
            logger.warning("External MCP server %s has no command", name)
            continue
        result[name] = {
            "type": "local",
            "command": command,
            "environment": dict(server.get("env") or {}),
            "enabled": True,
            "timeout": 60000,
        }
    return result


def write_opencode_config(
    session_dir: Path,
    *,
    tool_names: list[str] | set[str] | None = None,
    mcp_servers: list[str] | set[str] | None = None,
    run_id: str | None = None,
) -> Path:
    """Write a scoped OpenCode config into the current session workspace.

    IF local tools are grouped by their backing ``tools/<folder>`` MCP server and
    filtered with ``IF_MCP_ALLOWED_TOOLS`` so the server only lists the selected
    specialist's declared tool names. Explicit ``mcp_servers`` remain for
    external MCP servers such as AWS docs and Yahoo Finance.

    When ``run_id`` is provided, the config is written to
    ``.if/opencode.run.<run_id>.json`` instead of the root
    ``session_dir/opencode.json``. This prevents concurrent runs in the
    same shared workspace from clobbering each other's MCP configuration.
    The per-run path should be passed to ``run_opencode()`` via the
    ``config_path`` parameter, which sets ``OPENCODE_CONFIG`` in the
    subprocess environment.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    tool_set = {
        name
        for name in (tool_names or [])
        if name and not name.startswith(("read_", "write_", "search_", "terminal_"))
    }
    explicit_servers = {name for name in (mcp_servers or []) if name}

    local_categories: set[str] = set()
    by_category: dict[str, list[str]] = {}
    try:
        local_categories = set(get_mcp_manager().categories)
    except Exception:
        local_categories = set()
    if tool_set:
        try:
            manager = get_mcp_manager()
            local_categories = set(manager.categories)
            categories = manager.categories_for_names(tool_set)
        except Exception as exc:
            logger.warning("Could not resolve MCP categories for OpenCode config: %s", exc)
            categories = {}
        for tool_name, category in categories.items():
            by_category.setdefault(category, []).append(tool_name)

    mcp: dict[str, dict[str, Any]] = {}
    for category, names in sorted(by_category.items()):
        mcp[f"if_{category}"] = _if_mcp_server(category, names)

    external_names = explicit_servers - set(by_category) - local_categories
    mcp.update(_external_mcp_servers(external_names))

    config = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": mcp,
    }
    if run_id:
        state_dir = session_dir / ".if"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / f"opencode.run.{run_id}.json"
    else:
        path = session_dir / "opencode.json"
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
