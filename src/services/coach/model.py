import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


SECRET_ENV = ("INTERNAL_API_TOKEN", "PL_PRINCIPAL_SECRET", "DISCORD_TOKEN", "CODEX_API_KEY")
SECRET_PREFIXES = ("AWS_", "OPENAI_", "OPENROUTER_")
LOCKED_FEATURES = (
    'forced_login_method="chatgpt"',
    "features.shell_tool=false",
    "features.apps=false",
    "features.plugins=false",
    "features.memory_tool=false",
    "features.request_permissions_tool=false",
    "features.multi_agent=false",
    'project_root_markers=[".codex"]',
)


class ModelError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ToolServer:
    url: str
    token: str


@dataclass(frozen=True)
class Reply:
    text: str
    thread_id: str


class Model(Protocol):
    async def complete(self, instructions: str, prompt: str) -> str: ...

    async def converse(self, workspace: Path, thread_id: str | None, instructions: str, prompt: str, tools: ToolServer) -> Reply: ...


def _environment() -> dict[str, str]:
    return {key: "" if key in SECRET_ENV or key.startswith(SECRET_PREFIXES) else value for key, value in os.environ.items()}


def _tool_overrides(tools: ToolServer) -> tuple[str, ...]:
    return (
        "mcp_servers.powerlifting.url=" + json.dumps(tools.url),
        "mcp_servers.powerlifting.http_headers={Authorization=" + json.dumps("Bearer " + tools.token) + "}",
        'mcp_servers.powerlifting.default_tools_approval_mode="approve"',
    )


def workspace_for(root: Path, owner: str, conversation_id: str) -> Path:
    path = root / hashlib.sha256(f"{owner}\0{conversation_id}".encode()).hexdigest()[:32]
    (path / ".codex").mkdir(parents=True, exist_ok=True)
    return path


class CodexModel:
    def __init__(self, model: str, effort: str, scratch: Path):
        self.model = model
        self.effort = effort
        self.scratch = scratch

    def _config(self, cwd: Path, overrides: tuple[str, ...] = ()):
        from openai_codex import CodexConfig

        Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).mkdir(parents=True, exist_ok=True)
        trust = "projects={" + json.dumps(str(cwd)) + '={trust_level="trusted"}}'
        return CodexConfig(cwd=str(cwd), env=_environment(), config_overrides=LOCKED_FEATURES + (trust,) + overrides)

    async def _check_subscription(self, codex) -> None:
        try:
            account = await codex.account()
        except Exception as exc:
            raise ModelError("auth_unavailable", "Coach Codex login is missing; run python -m services.coach.login in the coach pod") from exc
        kind = getattr(getattr(getattr(account, "account", None), "root", None), "type", None)
        if getattr(kind, "value", kind) != "chatgpt":
            raise ModelError("subscription_required", "Coach requires ChatGPT subscription login")

    async def _run(self, cwd: Path, overrides: tuple[str, ...], thread_id: str | None, instructions: str, prompt: str, ephemeral: bool = False) -> Reply:
        from openai_codex import ApprovalMode, AsyncCodex, Sandbox

        async with AsyncCodex(self._config(cwd, overrides)) as codex:
            await self._check_subscription(codex)
            options = dict(model=self.model, cwd=str(cwd), sandbox=Sandbox.read_only, approval_mode=ApprovalMode.deny_all, developer_instructions=instructions)
            thread = await codex.thread_resume(thread_id, **options) if thread_id else await codex.thread_start(ephemeral=ephemeral, **options)
            result = await thread.run(prompt, model=self.model, effort=self.effort)
        if result.error:
            raise ModelError("model_failed", result.error.message)
        if getattr(result.status, "value", result.status) != "completed":
            raise ModelError("interrupted", "Coach turn did not complete; check side effects before retrying")
        return Reply(text=result.final_response or "", thread_id=thread.id)

    async def complete(self, instructions: str, prompt: str) -> str:
        self.scratch.mkdir(parents=True, exist_ok=True)
        return (await self._run(self.scratch, (), None, instructions, prompt, ephemeral=True)).text

    async def converse(self, workspace: Path, thread_id: str | None, instructions: str, prompt: str, tools: ToolServer) -> Reply:
        return await self._run(workspace, _tool_overrides(tools), thread_id, instructions, prompt)
