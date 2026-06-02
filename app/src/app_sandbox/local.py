
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_manager: Optional["LocalSandboxManager"] = None

WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/app/src/data/conversations")

class LocalSandboxManager:


    def __init__(self, workspace_base: str = WORKSPACE_BASE):
        self.workspace_base = Path(workspace_base)

    def get_workspace(self, chat_id: str) -> Path:

        workdir = self.workspace_base / chat_id
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def get_working_dir(self, chat_id: str) -> str:

        return str(self.get_workspace(chat_id))

    def close(self) -> None:

        return None

def init_local_sandbox(workspace_base: str = WORKSPACE_BASE) -> LocalSandboxManager:

    global _manager
    _manager = LocalSandboxManager(workspace_base)
    Path(workspace_base).mkdir(parents=True, exist_ok=True)
    return _manager

def get_local_sandbox() -> LocalSandboxManager:

    if _manager is None:
        raise RuntimeError("LocalSandboxManager not initialized — call init_local_sandbox() first")
    return _manager
