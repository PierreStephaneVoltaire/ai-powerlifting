import hmac
import json
import logging
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field

from . import principal
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


class TurnRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(min_length=1)
    athlete: str = ""


def _conflicting_scope(value: Any, athlete: str) -> bool:
    if isinstance(value, dict):
        return any((key in SCOPE_KEYS and item != athlete) or _conflicting_scope(item, athlete) for key, item in value.items() if key != "_report_source")
    if isinstance(value, list):
        return any(_conflicting_scope(item, athlete) for item in value)
    return False


def _athlete_from(conversation_id: str, person: str) -> str:
    parts = conversation_id.split(":")
    return parts[1] if len(parts) >= 3 and parts[0] == "powerlifting" and parts[1] else person


def create_app(settings: Settings | None = None, model: Model | None = None, services: PowerliftingServices | None = None) -> FastAPI:
    settings = settings or load()
    services = services or PowerliftingServices(settings)
    runner = Runner(settings, model or CodexModel(settings.model, settings.effort, settings.state_dir / "scratch"), services, Store(settings.database))
    app = FastAPI(title="Powerlifting Coach")
    app.state.runner = runner

    def internal(x_internal_token: str = Header(default="")):
        if not settings.internal_token or not hmac.compare_digest(settings.internal_token, x_internal_token):
            raise HTTPException(401, "Invalid internal token")

    def person(_: None = Depends(internal), x_person_pk: str = Header(default="")) -> str:
        if not x_person_pk:
            raise HTTPException(403, "Authenticated Person scope required")
        return x_person_pk

    def verify(token: str, operation: str, owner: str, athlete: str) -> dict:
        try:
            return principal.verify(settings.principal_secret, token, operation, owner, athlete)
        except Exception as exc:
            raise HTTPException(401, "Verified acting Person required") from exc

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

    async def readable(job_id: str, owner: str, token: str, action: str = READ_ACTION) -> Job:
        job = job_or_404(job_id)
        if job.kind != "domain":
            if job.owner != owner:
                raise HTTPException(404, "Job not found")
            return job
        verify(token, action, owner, job.athlete)
        if action == CANCEL_ACTION and job.owner != owner:
            raise HTTPException(403, "Only the submitting Person may cancel this job")
        arguments = {**(job.payload.get("arguments") or {}), "cache_only": True, "refresh": False, "_required_access": job.payload.get("access_requirements")}
        await access(owner, job.athlete, job.payload["operation"], arguments)
        return job

    @app.get("/health")
    def health():
        return {"status": "ok", "operations": len(runner.catalog)}

    @app.post("/v1/jobs", status_code=202)
    async def submit(request: JobRequest, owner: str = Depends(person), x_pl_principal: str = Header(default="")):
        if request.kind != "domain":
            raise HTTPException(422, "Only domain jobs may be submitted; use conversation turns")
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
        claims = verify(x_pl_principal, operation.name, owner, athlete)
        internal_fields = {key for key in arguments if key.startswith("_")}
        if internal_fields - ({"_report_source"} if claims["iss"] == principal.SIGNING_ISSUER else set()):
            raise HTTPException(403, "Internal operation fields cannot be supplied")
        context = await access(owner, athlete, operation.name, arguments)
        payload["access_requirements"] = {
            "permissions": sorted(p for p in context.get("permissions", []) if p.endswith(":read") and p.split(":")[0] not in {"settings", "grants", "operator"}),
            "competition_ids": context.get("competition_scope", {}).get("read", []),
        }
        payload.update(domain=operation.domain, athlete=athlete)
        return runner.submit_domain(owner, athlete, payload).view()

    @app.get("/v1/jobs/{job_id}")
    async def status(job_id: str, owner: str = Depends(person), x_pl_principal: str = Header(default="")):
        return (await readable(job_id, owner, x_pl_principal)).view()

    @app.get("/v1/jobs/{job_id}/result")
    async def result(job_id: str, owner: str = Depends(person), x_pl_principal: str = Header(default="")):
        job = await readable(job_id, owner, x_pl_principal)
        return JSONResponse(job.view(), status_code=200 if job.status in TERMINAL else 202)

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel(job_id: str, owner: str = Depends(person), x_pl_principal: str = Header(default="")):
        job = await readable(job_id, owner, x_pl_principal, CANCEL_ACTION)
        runner.cancel(job.job_id)
        return job_or_404(job_id).view()

    @app.post("/v1/conversations/{conversation_id}/turns", status_code=202)
    async def turn(conversation_id: str, request: TurnRequest, owner: str = Depends(person)):
        athlete = request.athlete or _athlete_from(conversation_id, owner)
        if athlete != owner and not (await access(owner, athlete, "access_context", {})).get("permissions"):
            raise HTTPException(403, "No Grant for this Athlete")
        return runner.submit_turn(owner, athlete, conversation_id, request.messages).view()

    @app.delete("/v1/conversations/{conversation_id}")
    async def reset(conversation_id: str, owner: str = Depends(person)):
        runner.store.forget_thread(owner, conversation_id)
        return {"reset": True}

    @app.post("/v1/jobs/{job_id}/mcp")
    async def mcp(job_id: str, request: Request, authorization: str = Header(default="")):
        if not hmac.compare_digest("Bearer " + runner.tool_token(job_id), authorization):
            raise HTTPException(401, "Invalid tool scope")
        job = job_or_404(job_id)
        if job.kind != "conversation" or job.status != "running":
            raise HTTPException(409, "Conversation turn is not running")
        body = await request.json()
        request_id, method = body.get("id"), body.get("method")
        if request_id is None:
            return JSONResponse({}, status_code=202)
        if method == "initialize":
            outcome = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "powerlifting-coach", "version": "1.0.0"}}
        elif method == "ping":
            outcome = {}
        elif method == "tools/list":
            outcome = {"tools": [{"name": op.name, "description": op.description, "inputSchema": op.input_schema} for op in runner.catalog.values()]}
        elif method == "tools/call":
            params = body.get("params") or {}
            try:
                value = await runner.call_tool(job, params.get("name", ""), params.get("arguments") or {})
                outcome = {"content": [{"type": "text", "text": json.dumps(value, default=str)}], "isError": False}
            except Exception as exc:
                detail = {"error": exc.detail, "status": exc.status} if isinstance(exc, ServiceError) else {"error": str(exc)}
                outcome = {"content": [{"type": "text", "text": json.dumps(detail, default=str)}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": outcome}

    return app


def main() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()
