import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from services.lib import llm_log

from .config import AISettings, Provider


SECRET_ENV = ("DISCORD_TOKEN", "CODEX_API_KEY", "COACH_PROVIDER_KEYS")
PROVIDER_KEY_ENV = "CODEX_PROVIDER_API_KEY"
SECRET_PREFIXES = ("AWS_", "OPENAI_", "OPENROUTER_")
LOCKED_FEATURES = (
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
    async def complete(self, ai: AISettings, instructions: str, prompt: str, workspace: Path | None = None) -> str: ...

    async def converse(self, ai: AISettings, workspace: Path, thread_id: str | None, instructions: str, prompt: str, tools: ToolServer) -> Reply: ...


def _environment() -> dict[str, str]:
    return {key: "" if key in SECRET_ENV or key.startswith(SECRET_PREFIXES) else value for key, value in os.environ.items()}


def _provider_overrides(name: str, provider: Provider) -> tuple[str, ...]:
    if provider.subscription:
        return ('forced_login_method="chatgpt"',)
    definition = "{name=" + json.dumps(name) + ",base_url=" + json.dumps(provider.base_url) + ",env_key=" + json.dumps(PROVIDER_KEY_ENV) + ',wire_api="responses"}'
    return ("model_providers." + name + "=" + definition, "model_provider=" + json.dumps(name))


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
    def __init__(self, scratch: Path, providers: dict[str, Provider]):
        self.scratch = scratch
        self.providers = providers

    def _config(self, cwd: Path, overrides: tuple[str, ...] = (), provider: str | None = None):
        from openai_codex import CodexConfig

        Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).mkdir(parents=True, exist_ok=True)
        trust = "projects={" + json.dumps(str(cwd)) + '={trust_level="trusted"}}'
        env = _environment()
        selected = self.providers[provider] if provider else None
        if selected and not selected.subscription:
            env[PROVIDER_KEY_ENV] = selected.api_key
        chosen = _provider_overrides(provider, selected) if selected else ('forced_login_method="chatgpt"',)
        return CodexConfig(cwd=str(cwd), env=env, config_overrides=LOCKED_FEATURES + chosen + (trust,) + overrides)

    async def _check_subscription(self, codex) -> None:
        try:
            account = await codex.account()
        except Exception as exc:
            raise ModelError("auth_unavailable", "Coach Codex login is missing; run python -m services.coach.login in the coach pod") from exc
        kind = getattr(getattr(getattr(account, "account", None), "root", None), "type", None)
        if getattr(kind, "value", kind) != "chatgpt":
            raise ModelError("subscription_required", "Coach requires ChatGPT subscription login")

    async def _run(self, ai: AISettings, cwd: Path, overrides: tuple[str, ...], thread_id: str | None, instructions: str, prompt: str, ephemeral: bool = False) -> Reply:
        from openai_codex import ApprovalMode, AsyncCodex, Sandbox

        provider = self.providers[ai.provider]
        started = time.monotonic()
        async with AsyncCodex(self._config(cwd, overrides, ai.provider)) as codex:
            if provider.subscription:
                await self._check_subscription(codex)
            options = dict(model=ai.model, model_provider=None if provider.subscription else ai.provider, cwd=str(cwd), sandbox=Sandbox.read_only, approval_mode=ApprovalMode.deny_all, developer_instructions=instructions)
            thread = await codex.thread_resume(thread_id, **options) if thread_id else await codex.thread_start(ephemeral=ephemeral, **options)
            result = await thread.run(prompt, model=ai.model, effort=ai.effort)
        llm_log.emit(
            "llm_call",
            model=ai.model,
            provider=ai.provider,
            effort=ai.effort,
            thread_id=thread.id,
            resumed=bool(thread_id),
            status=getattr(result.status, "value", result.status),
            error=result.error.message if result.error else None,
            latency_ms=round((time.monotonic() - started) * 1000),
            instructions=instructions,
            prompt=prompt,
            response=result.final_response,
            **llm_log.usage_fields(result.usage),
        )
        if result.error:
            raise ModelError("model_failed", result.error.message)
        if getattr(result.status, "value", result.status) != "completed":
            raise ModelError("interrupted", "Coach turn did not complete; check side effects before retrying")
        return Reply(text=result.final_response or "", thread_id=thread.id)

    async def complete(self, ai: AISettings, instructions: str, prompt: str, workspace: Path | None = None) -> str:
        cwd = workspace or self.scratch
        cwd.mkdir(parents=True, exist_ok=True)
        return (await self._run(ai, cwd, (), None, instructions, prompt, ephemeral=True)).text

    async def converse(self, ai: AISettings, workspace: Path, thread_id: str | None, instructions: str, prompt: str, tools: ToolServer) -> Reply:
        return await self._run(ai, workspace, _tool_overrides(tools), thread_id, instructions, prompt)
