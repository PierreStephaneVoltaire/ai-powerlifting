import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from .catalog import Operation, operations
from .config import Settings
from .model import Model, ModelError, ToolServer, workspace_for
from .operations import run_operation
from .services import PowerliftingServices, Scope, ServiceError
from .store import Job, Store


logger = logging.getLogger("coach")
INSTRUCTIONS = (Path(__file__).with_name("instructions.md")).read_text()
HISTORY_LIMIT = 40


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(str(part.get("text", "")) for part in content or [] if isinstance(part, dict))


def _failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ModelError):
        return {"code": exc.code, "message": str(exc)}
    if isinstance(exc, ServiceError):
        return {"code": "service_error", "message": str(exc), "status": exc.status}
    return {"code": "execution_failed", "message": str(exc)}


class LimitedModel:
    def __init__(self, model: Model, limit: int):
        self.model = model
        self.completions = asyncio.Semaphore(limit)
        self.conversations = asyncio.Semaphore(limit)

    async def complete(self, instructions: str, prompt: str) -> str:
        async with self.completions:
            return await self.model.complete(instructions, prompt)

    async def converse(self, *args, **kwargs):
        async with self.conversations:
            return await self.model.converse(*args, **kwargs)


class Runner:
    def __init__(self, settings: Settings, model: Model, services: PowerliftingServices, store: Store):
        self.settings = settings
        self.model = LimitedModel(model, settings.max_concurrent_turns)
        self.services = services
        self.store = store
        self.tasks: dict[str, asyncio.Task] = {}

    @property
    def catalog(self) -> dict[str, Operation]:
        return operations(self.settings.operations_dir, self.settings.permissions_path)

    def tool_token(self, job_id: str) -> str:
        return hmac.new(self.settings.internal_token.encode(), f"coach-tools:{job_id}".encode(), hashlib.sha256).hexdigest()

    def _spawn(self, job: Job, work) -> None:
        async def execute():
            job.status = "running"
            self.store.update(job)
            try:
                job.result = await work()
                job.status = "succeeded"
            except asyncio.CancelledError:
                job.status, job.error = "cancelled", {"code": "cancelled", "message": "Cancelled; check side effects before retrying"}
            except Exception as exc:
                logger.exception("job %s failed", job.job_id)
                job.status, job.error = ("uncertain" if job.kind == "conversation" else "failed"), _failure(exc)
            finally:
                self.store.update(job)
                self.tasks.pop(job.job_id, None)

        self.tasks[job.job_id] = asyncio.create_task(execute())

    def submit_domain(self, owner: str, athlete: str, payload: dict[str, Any]) -> Job:
        operation = self.catalog[payload["operation"]]
        job = self.store.create(owner, athlete, "domain", f"powerlifting:{athlete}:{uuid.uuid4().hex}", payload)
        scope = Scope(person=owner, athlete=athlete)
        generation = {"generation_id": payload["generation_id"], "generation_attempt": payload.get("generation_attempt", 0)} if payload.get("generation_id") else None
        self._spawn(job, lambda: run_operation(self.services, self.model, scope, operation, payload.get("arguments") or {}, job.job_id, generation))
        return job

    def submit_turn(self, owner: str, athlete: str, conversation_id: str, messages: list[dict[str, Any]]) -> Job:
        job = self.store.create(owner, athlete, "conversation", conversation_id, {"messages": messages[-HISTORY_LIMIT:]})
        self._spawn(job, lambda: self._converse(job))
        return job

    async def _converse(self, job: Job) -> str:
        messages = job.payload["messages"]
        latest = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if latest is None:
            raise ModelError("invalid_input", "A user message is required")
        thread_id = self.store.thread(job.owner, job.conversation_id)
        prompt = _text(latest.get("content"))
        earlier = [m for m in messages[: messages.index(latest)] if m.get("role") in {"user", "assistant"}]
        if not thread_id and earlier:
            transcript = "\n\n".join(f"[{m['role']}] {_text(m.get('content'))}" for m in earlier)
            prompt = f"Earlier in this conversation:\n{transcript}\n\nLatest message:\n{prompt}"
        context = json.dumps({"person": job.owner, "athlete": job.athlete, "today": date.today().isoformat()})
        tools = ToolServer(url=f"{self.settings.public_url}/v1/jobs/{job.job_id}/mcp", token=self.tool_token(job.job_id))
        workspace = workspace_for(self.settings.workspaces, job.owner, job.conversation_id)
        reply = await self.model.converse(workspace, thread_id, INSTRUCTIONS + "\n\nScope for this conversation: " + context, prompt, tools)
        self.store.bind_thread(job.owner, job.conversation_id, reply.thread_id)
        return reply.text

    async def call_tool(self, job: Job, name: str, arguments: dict[str, Any]) -> Any:
        operation = self.catalog.get(name)
        if operation is None:
            raise ModelError("unknown_tool", f"Unknown tool {name}")
        arguments = {key: value for key, value in arguments.items() if not key.startswith("_")}
        scope = Scope(person=job.owner, athlete=job.athlete)
        return await run_operation(self.services, self.model, scope, operation, arguments, f"{job.job_id}-{uuid.uuid4().hex[:12]}")

    def cancel(self, job_id: str) -> None:
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
