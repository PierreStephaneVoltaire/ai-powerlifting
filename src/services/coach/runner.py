import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from services.runtime import llm_log

from .catalog import Operation, operations
from .config import AISettings, Provider, Settings
from .lifetime import with_lifetime_report
from .model import Model, ModelError
from .operations import run_operation
from .services import PowerliftingServices, Scope, ServiceError
from .store import Job, Store


logger = logging.getLogger("coach")


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

    async def complete(self, ai: AISettings, instructions: str, prompt: str, workspace: Path | None = None) -> str:
        async with self.slots[ai.provider]:
            if workspace is None:
                return await self.model.complete(ai, instructions, prompt)
            return await self.model.complete(ai, instructions, prompt, workspace=workspace)


class Runner:
    def __init__(self, settings: Settings, model: Model, services: PowerliftingServices, store: Store):
        missing = sorted(name for name, operation in operations(settings.operations_dir, settings.permissions_path).items() if operation.uses_inference and name not in settings.operation_ai)
        if missing:
            raise ValueError("COACH_OPERATION_AI has no model and effort for: " + ", ".join(missing))
        unknown = sorted({ai.provider for ai in settings.operation_ai.values()} - settings.providers.keys())
        if unknown:
            raise ValueError("Unknown Coach providers: " + ", ".join(unknown))
        self.settings = settings
        self.model = LimitedModel(model, settings.providers)
        self.services = services
        self.store = store
        self.tasks: dict[str, asyncio.Task] = {}

    @property
    def catalog(self) -> dict[str, Operation]:
        return operations(self.settings.operations_dir, self.settings.permissions_path)

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
                job.status, job.error = "failed", _failure(exc)
            finally:
                self.store.update(job)
                self.tasks.pop(job.job_id, None)

        self.tasks[job.job_id] = asyncio.create_task(execute())

    def submit_domain(self, owner: str, athlete: str, payload: dict[str, Any], job_id: str = '') -> Job:
        operation = self.catalog[payload["operation"]]
        job = self.store.create(owner, athlete, "domain", f"powerlifting:{athlete}:{uuid.uuid4().hex}", payload, job_id)
        scope = Scope(person=owner, athlete=athlete, job_id=job.job_id)
        generation = {"generation_id": payload["generation_id"], "generation_attempt": payload.get("generation_attempt", 0)} if payload.get("generation_id") else None
        async def work():
            with llm_log.scope(kind="operation", operation=operation.name, job_id=job.job_id, person=owner, athlete=athlete):
                model = await with_lifetime_report(self.settings, self.model, job) if operation.name == "template_evaluate" else self.model
                return await run_operation(self.services, model, self.settings.operation_ai, scope, operation, payload.get("arguments") or {}, job.job_id, generation)

        self._spawn(job, work)
        return job

    def cancel(self, job_id: str) -> None:
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
