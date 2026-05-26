"""LocalSandbox directory manager for per-conversation file access."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_manager: Optional["LocalSandboxManager"] = None

WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/app/src/data/conversations")


class LocalSandboxManager:
    """Manages per-conversation local directories."""

    def __init__(self, workspace_base: str = WORKSPACE_BASE):
        self.workspace_base = Path(workspace_base)

    def get_workspace(self, chat_id: str) -> Path:
        """Return (creating if needed) the local directory for this conversation."""
        workdir = self.workspace_base / chat_id
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def get_working_dir(self, chat_id: str) -> str:
        """Return the working directory path for a conversation."""
        return str(self.get_workspace(chat_id))

    def close(self) -> None:
        """Directory manager has no persistent process resources."""
        return None


def init_local_sandbox(workspace_base: str = WORKSPACE_BASE) -> LocalSandboxManager:
    """Initialize the global LocalSandboxManager. Call once at startup."""
    global _manager
    _manager = LocalSandboxManager(workspace_base)
    Path(workspace_base).mkdir(parents=True, exist_ok=True)
    return _manager


def get_local_sandbox() -> LocalSandboxManager:
    """Return the global LocalSandboxManager. Raises if not initialized."""
    if _manager is None:
        raise RuntimeError("LocalSandboxManager not initialized — call init_local_sandbox() first")
    return _manager
