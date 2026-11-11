import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from services.lib import llm_log
from services.lib.template_patch import patch_hash

from . import chat_cache, guard
from .catalog import Operation, operations
from .config import AISettings, Provider, Settings
from .model import Model, ModelError, ToolServer, workspace_for
from .operations import run_operation
from .services import PowerliftingServices, Scope, ServiceError
from .store import Binding, Job, Store
from .surfaces import SURFACES, Surface, tools


logger = logging.getLogger("coach")
INSTRUCTIONS = (Path(__file__).with_name("instructions.md")).read_text()
HISTORY_LIMIT = 40
GUARD_AI = "chat_guard"
CACHEABLE_INTENTS = frozenset({"explain", "challenge_finding", "other"})


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
    def __init__(self, model: Model, providers: dict[str, Provider]):
        self.model = model
        self.slots = {name: asyncio.Semaphore(provider.max_concurrent) for name, provider in providers.items()}

    async def complete(self, ai: AISettings, instructions: str, prompt: str) -> str:
        async with self.slots[ai.provider]:
            return await self.model.complete(ai, instructions, prompt)

    async def converse(self, ai: AISettings, *args, **kwargs):
        async with self.slots[ai.provider]:
            return await self.model.converse(ai, *args, **kwargs)


class Runner:
    def __init__(self, settings: Settings, model: Model, services: PowerliftingServices, store: Store):
        missing = sorted([name for name, operation in operations(settings.operations_dir, settings.permissions_path).items() if operation.uses_inference and name not in settings.operation_ai] + ([] if GUARD_AI in settings.operation_ai else [GUARD_AI]))
        if missing:
            raise ValueError("COACH_OPERATION_AI has no model and effort for: " + ", ".join(missing))
        unknown = sorted({ai.provider for ai in (settings.conversation_ai, *settings.operation_ai.values())} - settings.providers.keys())
        if unknown:
            raise ValueError("Unknown Coach providers: " + ", ".join(unknown))
        self.settings = settings
        self.model = LimitedModel(model, settings.providers)
        self.services = services
        self.store = store
        self.tasks: dict[str, asyncio.Task] = {}
        self.limiter = guard.RateLimiter()
        self.tool_secret = secrets.token_bytes(32)

    @property
    def catalog(self) -> dict[str, Operation]:
        return operations(self.settings.operations_dir, self.settings.permissions_path)

    def tool_token(self, job_id: str) -> str:
        return hmac.new(self.tool_secret, f"coach-tools:{job_id}".encode(), hashlib.sha256).hexdigest()

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

    def submit_domain(self, owner: str, athlete: str, payload: dict[str, Any], job_id: str = '', capability: str = '') -> Job:
        operation = self.catalog[payload["operation"]]
        payload = {**payload, "_job_capability": capability}
        job = self.store.create(owner, athlete, "domain", f"powerlifting:{athlete}:{uuid.uuid4().hex}", payload, job_id)
        scope = Scope(person=owner, athlete=athlete, capability=capability, job_id=job.job_id)
        generation = {"generation_id": payload["generation_id"], "generation_attempt": payload.get("generation_attempt", 0)} if payload.get("generation_id") else None
        async def work():
            with llm_log.scope(kind="operation", operation=operation.name, job_id=job.job_id, person=owner, athlete=athlete):
                return await run_operation(self.services, self.model, self.settings.operation_ai, scope, operation, payload.get("arguments") or {}, job.job_id, generation)

        self._spawn(job, work)
        return job

    def surface_tools(self, job: Job) -> dict[str, Operation]:
        return tools(self.catalog, SURFACES.get(job.payload.get("surface") or ""))

    def submit_turn(self, owner: str, athlete: str, conversation_id: str, messages: list[dict[str, Any]], surface: str | None = None, subject: str | None = None, job_id: str = '', capability: str = '') -> Job:
        if surface:
            current = self.store.binding(owner, conversation_id)
            if not current or current.surface != surface or current.subject != subject:
                self.store.bind(owner, conversation_id, Binding(surface=surface, subject=subject or "", locked=True))
        job = self.store.create(owner, athlete, "conversation", conversation_id, {"messages": messages[-HISTORY_LIMIT:], "_job_capability": capability}, job_id)
        async def work():
            with llm_log.scope(kind="conversation", conversation_id=conversation_id, job_id=job.job_id, person=owner, athlete=athlete):
                return await self._converse(job)

        self._spawn(job, work)
        return job

    async def _converse(self, job: Job) -> str:
        messages = job.payload["messages"]
        latest = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if latest is None:
            raise ModelError("invalid_input", "A user message is required")
        message = _text(latest.get("content"))
        person, athlete = await self._identity(job)
        with llm_log.scope(person=person, athlete=athlete):
            return await self._route(job, messages, latest, message, person)

    async def _identity(self, job: Job) -> tuple[str, str]:
        access = await self.services.access(Scope(person=job.owner, athlete=job.athlete, capability=job.payload.get("_job_capability", ""), job_id=job.job_id), "access_context", {})
        return str(access.get("settings_pk") or job.owner), str(access.get("own_athlete_pk") or job.athlete)

    async def _route(self, job: Job, messages: list[dict[str, Any]], latest: dict[str, Any], message: str, person: str) -> str:
        rejection = guard.check_rules(person, message, self.limiter)
        if rejection:
            return self._finish(job, message, rejection.reply, outcome=f"rejected:{rejection.code}")
        binding = self.store.binding(job.owner, job.conversation_id)
        templates = await self._templates(job)
        names = {template.get("sk"): template.get("name") for template in templates}
        state = {
            "bound_template": names.get(binding.subject) if binding and binding.surface == "template" else None,
            "awaiting_confirmation": bool(binding and binding.preview_hash),
            "previous_reply": next((_text(m.get("content"))[:500] for m in reversed(messages[: messages.index(latest)]) if m.get("role") == "assistant"), None),
        }
        with llm_log.scope(stage="guard"):
            verdict = await guard.classify(self.model, self.settings.operation_ai[GUARD_AI], message, [name for name in names.values() if name], state)
        if verdict.surface == "out_of_scope":
            return self._finish(job, message, guard.REFUSALS["out_of_scope"], outcome="rejected:out_of_scope", verdict=verdict)
        if binding and binding.locked:
            if verdict.surface != "template":
                return self._finish(job, message, guard.REFUSALS["locked"], outcome="rejected:locked", verdict=verdict)
            return await self._template_turn(job, message, binding, verdict, messages, latest)
        if verdict.surface == "template":
            bound = binding if binding and binding.surface == "template" else None
            if not bound or (verdict.template_name and guard._key(verdict.template_name) != guard._key(names.get(bound.subject) or "")):
                matches = guard.match_templates(verdict.template_name, templates)
                if len(matches) != 1:
                    return self._finish(job, message, guard.candidates_reply(verdict.template_name, matches, templates), outcome="needs_template", verdict=verdict)
                bound = Binding(surface="template", subject=matches[0]["sk"])
                self.store.bind(job.owner, job.conversation_id, bound)
            return await self._template_turn(job, message, bound, verdict, messages, latest)
        if binding:
            self.store.bind(job.owner, job.conversation_id, None)
        reply = await self._agent(job, None, INSTRUCTIONS, {}, messages, latest)
        return self._finish(job, message, reply, outcome="accepted", verdict=verdict, surface="general")

    async def _template_turn(self, job: Job, message: str, binding: Binding, verdict: guard.Verdict, messages: list[dict[str, Any]], latest: dict[str, Any]) -> str:
        surface = SURFACES["template"]
        scope = Scope(person=job.owner, athlete=job.athlete, capability=job.payload.get("_job_capability", ""), job_id=job.job_id)
        template = await self.services.call(scope, "templates", "template_get", {"sk": binding.subject})
        version = chat_cache.fingerprint(template)
        cacheable = verdict.standalone and verdict.intent in CACHEABLE_INTENTS
        if cacheable:
            hit = await chat_cache.lookup(version, verdict.intent, message)
            if hit:
                return self._finish(job, message, hit[1], outcome="accepted", verdict=verdict, surface=surface.name, subject=binding.subject, cache_layer=hit[0])
        job.payload.update(surface=surface.name, subject=binding.subject, intent=verdict.intent)
        self.store.update(job)
        extra = {"template_sk": binding.subject, "template_name": (template.get("meta") or {}).get("name")}
        reply = await self._agent(job, surface, surface.instructions, extra, messages, latest)
        if cacheable:
            await chat_cache.remember(version, verdict.intent, message, reply)
        return self._finish(job, message, reply, outcome="accepted", verdict=verdict, surface=surface.name, subject=binding.subject, cache_layer="none")

    async def _templates(self, job: Job) -> list[dict[str, Any]]:
        listed = await self.services.call(Scope(person=job.owner, athlete=job.athlete, capability=job.payload.get("_job_capability", ""), job_id=job.job_id), "templates", "template_list", {})
        return listed if isinstance(listed, list) else []

    async def _agent(self, job: Job, surface: Surface | None, instructions: str, extra: dict[str, Any], messages: list[dict[str, Any]], latest: dict[str, Any]) -> str:
        thread_id = self.store.thread(job.owner, job.conversation_id)
        prompt = _text(latest.get("content"))
        earlier = [m for m in messages[: messages.index(latest)] if m.get("role") in {"user", "assistant"}]
        if not thread_id and earlier:
            transcript = "\n\n".join(f"[{m['role']}] {_text(m.get('content'))}" for m in earlier)
            prompt = f"Earlier in this conversation:\n{transcript}\n\nLatest message:\n{prompt}"
        context = json.dumps({"person": job.owner, "athlete": job.athlete, "today": date.today().isoformat(), **extra})
        tool_server = ToolServer(url=f"{self.settings.public_url}/v1/jobs/{job.job_id}/mcp", token=self.tool_token(job.job_id))
        workspace = workspace_for(self.settings.workspaces, job.owner, job.conversation_id)
        with llm_log.scope(stage="agent", surface=surface.name if surface else "general"):
            reply = await self.model.converse(self.settings.conversation_ai, workspace, thread_id, instructions + "\n\nScope for this conversation: " + context, prompt, tool_server)
        self.store.bind_thread(job.owner, job.conversation_id, reply.thread_id)
        return reply.text

    def _finish(self, job: Job, message: str, reply: str, outcome: str, verdict: guard.Verdict | None = None, **fields: Any) -> str:
        llm_log.emit(
            "chat_turn",
            guard=outcome,
            intent=verdict.intent if verdict else None,
            routed_surface=verdict.surface if verdict else None,
            template_name=verdict.template_name if verdict else None,
            standalone=verdict.standalone if verdict else None,
            guard_reason=verdict.reason if verdict else None,
            message=message,
            reply=reply,
            **fields,
        )
        return reply

    async def call_tool(self, job: Job, name: str, arguments: dict[str, Any]) -> Any:
        operation = self.surface_tools(job).get(name)
        if operation is None:
            raise ModelError("unknown_tool", f"Tool {name} is not available in this conversation")
        arguments = {key: value for key, value in arguments.items() if not key.startswith("_")}
        surface = SURFACES.get(job.payload.get("surface") or "")
        if surface:
            arguments[surface.subject_argument] = job.payload["subject"]
        if name == "template_patch":
            self._check_patch(job, arguments)
        scope = Scope(person=job.owner, athlete=job.athlete, capability=job.payload.get("_job_capability", ""), job_id=job.job_id)
        with llm_log.scope(kind="tool", operation=name, conversation_id=job.conversation_id, job_id=job.job_id, person=job.owner, athlete=job.athlete):
            result = await run_operation(self.services, self.model.model, self.settings.operation_ai, scope, operation, arguments, f"{job.job_id}-{uuid.uuid4().hex[:12]}")
            llm_log.emit("chat_tool", arguments=arguments, result=result)
        if name == "template_patch" and isinstance(result, dict):
            binding = self.store.binding(job.owner, job.conversation_id)
            if binding:
                binding.preview_hash = None if result.get("applied") else result.get("preview_hash")
                self.store.bind(job.owner, job.conversation_id, binding)
        return result

    def _check_patch(self, job: Job, arguments: dict[str, Any]) -> None:
        if not arguments.get("apply"):
            return
        binding = self.store.binding(job.owner, job.conversation_id)
        digest = patch_hash(arguments["sk"], arguments.get("operations") or [])
        if job.payload.get("intent") != "confirm" or not binding or binding.preview_hash != digest:
            raise ModelError("confirmation_required", "Apply only the exact operations previewed in the previous turn, after the Person confirms them")

    def cancel(self, job_id: str) -> None:
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
