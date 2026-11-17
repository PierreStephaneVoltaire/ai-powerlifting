import logging
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from jsonschema import ValidationError, validate
from pydantic import BaseModel

from services.runtime.mesh import caller
from .config import Settings, load
from .model import CodexModel, Model
from .runner import Runner
from .services import PowerliftingServices, Scope, ServiceError
from .store import TERMINAL, Job, Store


SCOPE_KEYS = {"athlete", "pk", "user_pk", "mapped_pk", "person_pk", "_user_pk"}
READ_ACTION = "domain_job_read"
CANCEL_ACTION = "domain_job_cancel"


class JobRequest(BaseModel):
    kind: str
    payload: dict[str, Any]
    conversation_id: str = ""


def _conflicting_scope(value: Any, athlete: str) -> bool:
    if isinstance(value, dict):
        return any((key in SCOPE_KEYS and item != athlete) or _conflicting_scope(item, athlete) for key, item in value.items() if key != "_report_source")
    if isinstance(value, list):
        return any(_conflicting_scope(item, athlete) for item in value)
    return False


def create_app(settings: Settings | None = None, model: Model | None = None, services: PowerliftingServices | None = None) -> FastAPI:
    settings = settings or load()
    services = services or PowerliftingServices(settings)
    runner = Runner(settings, model or CodexModel(settings.state_dir / "scratch", settings.providers), services, Store(settings.database))
    app = FastAPI(title="Powerlifting Coach")
    app.state.runner = runner

    def person(x_person_pk: str = Header(default="")) -> str:
        if not x_person_pk:
            raise HTTPException(403, "Authenticated Person scope required")
        return x_person_pk

    async def access(owner: str, athlete: str, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return await services.access(Scope(person=owner, athlete=athlete), operation, arguments)
        except ServiceError as exc:
            raise HTTPException(exc.status if exc.status in {401, 403} else 503, "Powerlifting operation access denied") from exc

    def job_or_404(job_id: str) -> Job:
        job = runner.store.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return job

    async def readable(job_id: str, owner: str, action: str = READ_ACTION) -> Job:
        job = job_or_404(job_id)
        if job.kind != "domain":
            if job.owner != owner:
                raise HTTPException(404, "Job not found")
            return job
        if action == CANCEL_ACTION and job.owner != owner:
            raise HTTPException(403, "Only the submitting Person may cancel this job")
        arguments = {**(job.payload.get("arguments") or {}), "cache_only": True, "refresh": False, "_required_access": job.payload.get("access_requirements")}
        await access(owner, job.athlete, job.payload["operation"], arguments)
        return job

    @app.get("/health")
    def health():
        return {"status": "ok", "operations": len(runner.catalog)}

    @app.post("/v1/jobs", status_code=202)
    async def submit(request: JobRequest, owner: str = Depends(person), x_pl_source_principal: str = Header(default="")):
        if request.kind != "domain":
            raise HTTPException(422, "Only domain jobs may be submitted")
        payload = dict(request.payload)
        operation = runner.catalog.get(payload.get("operation", ""))
        if operation is None:
            raise HTTPException(422, "Unknown domain operation")
        arguments = payload.get("arguments") or {}
        try:
            validate(arguments, operation.input_schema)
        except ValidationError as exc:
            raise HTTPException(422, exc.message) from exc
        athlete = payload.get("athlete")
        if not isinstance(athlete, str) or not athlete:
            raise HTTPException(422, "Authenticated Athlete scope required")
        if _conflicting_scope(arguments, athlete):
            raise HTTPException(403, "Job payload scope conflicts with authenticated Athlete")
        internal_fields = {key for key in arguments if key.startswith("_")}
        if internal_fields - ({"_report_source"} if caller(x_pl_source_principal).endswith('/sa/pl-' + operation.domain) else set()):
            raise HTTPException(403, "Internal operation fields cannot be supplied")
        context = await access(owner, athlete, operation.name, arguments)
        if operation.uses_inference and "ai:use" not in context.get("permissions", []):
            raise HTTPException(403, "AI access requires the pro group")
        payload["access_requirements"] = {
            "permissions": sorted(p for p in context.get("permissions", []) if p.endswith(":read") and p.split(":")[0] not in {"settings", "grants", "operator"}),
            "competition_ids": context.get("competition_scope", {}).get("read", []),
        }
        payload.update(domain=operation.domain, athlete=athlete)
        return runner.submit_domain(owner, athlete, payload, uuid.uuid4().hex).view()

    @app.get("/v1/jobs/{job_id}")
    async def status(job_id: str, owner: str = Depends(person)):
        return (await readable(job_id, owner)).view()

    @app.get("/v1/jobs/{job_id}/result")
    async def result(job_id: str, owner: str = Depends(person)):
        job = await readable(job_id, owner)
        return JSONResponse(job.view(), status_code=200 if job.status in TERMINAL else 202)

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel(job_id: str, owner: str = Depends(person)):
        job = await readable(job_id, owner, CANCEL_ACTION)
        runner.cancel(job.job_id)
        return job_or_404(job_id).view()

    return app


def main() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
