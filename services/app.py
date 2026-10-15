import asyncio
import hmac
import json
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from jsonschema import ValidationError

from .contract import JOB_SUBMITTED_SCHEMA, load_operations
from .dispatch import OperationError, authorize, dispatch
from . import execution
from .authorization import authorize_request
from .access import permission_map
from services.lib.program_store import ProgramRevisionConflictError
from services.lib.session_store import SessionRevisionConflictError


DOMAIN = os.environ["PL_DOMAIN"]
OPERATIONS = load_operations(DOMAIN)
app = FastAPI(title=f"Powerlifting {DOMAIN}")


def authenticate(x_internal_token: str = Header(default="")):
    expected = os.getenv("INTERNAL_API_TOKEN", "")
    if not expected or not hmac.compare_digest(expected, x_internal_token):
        raise HTTPException(401, "Invalid internal token")


@app.get("/health")
def health():
    return {"status": "ok", "domain": DOMAIN}


async def call(name: str, arguments: dict[str, Any], athlete: str, person: str, job_id: str = "", nested_operation: bool = False, generation_id: str = "", generation_attempt: int = 0, principal: str = ""):
    if generation_id and not job_id:
        raise HTTPException(403, "Generation requires an active native turn")
    if name not in OPERATIONS:
        raise HTTPException(404, "Unknown operation")
    operation = OPERATIONS[name]
    access = {}
    try:
        claims, access = await authorize_request(name, arguments, principal, person, athlete)
        person, athlete = claims['sub'], claims['athlete']
        arguments = authorize(operation, arguments, athlete, person, access)
        operation.validate_input(arguments)
        arguments['_person_pk'] = person
        arguments['_access'] = access
        if job_id:
            arguments["_if_job_id"] = job_id
            if generation_id:
                arguments["_generation_id"] = generation_id
                arguments["_generation_attempt"] = generation_attempt
        if nested_operation:
            if not job_id:
                raise OperationError(409, "uncertain", "Nested operation requires an active domain execution")
            return await execution.dispatch_nested(operation, arguments, athlete, job_id)
        if job_id:
            return await execution.start(operation, arguments, athlete, job_id)
        if operation.execution == "ai":
            return await execution.submit(operation, arguments, athlete, person)
        return await asyncio.to_thread(dispatch, operation, arguments)
    except OperationError as exc:
        details = dict(exc.details)
        record = details.get('current_record')
        if isinstance(record, dict):
            from .publication import program_view, session_view
            if 'meta' in record and (operation.domain != 'templates' or name == 'template_apply_confirm'):
                details['current_record'] = program_view(record, access)
            elif operation.domain == 'sessions':
                details['current_record'] = session_view(record, access)
        raise HTTPException(exc.status, jsonable_encoder({"code": exc.code, "message": exc.message, **details}))
    except ProgramRevisionConflictError as exc:
        from .publication import program_view
        record = program_view(exc.current_record, access) if isinstance(exc.current_record, dict) else exc.current_record
        raise HTTPException(409, jsonable_encoder({'code': getattr(exc, 'code', 'conflict'), 'message': str(exc), 'current_revision': exc.current_revision, 'current_record': record}))
    except SessionRevisionConflictError as exc:
        from .publication import session_view
        record = session_view(exc.current_record, access) if isinstance(exc.current_record, dict) else exc.current_record
        raise HTTPException(409, jsonable_encoder({'code': getattr(exc, 'code', 'conflict'), 'message': str(exc), 'current_revision': exc.current_revision, 'current_record': record}))
    except ValidationError as exc:
        raise HTTPException(422, {"code": "validation", "message": exc.message})
    except ValueError as exc:
        raise HTTPException(422, {"code": "validation", "message": str(exc)})


@app.post("/operations/{name}", dependencies=[Depends(authenticate)])
async def operation(name: str, arguments: dict[str, Any], x_athlete_pk: str = Header(default=""), x_person_pk: str = Header(default=""), x_if_job_id: str = Header(default=""), x_pl_nested_operation: str = Header(default=""), x_if_turn_id: str = Header(default=""), x_if_generation_id: str = Header(default=""), x_if_generation_attempt: int = Header(default=0), x_pl_principal: str = Header(default="")):
    result = await call(name, arguments, x_athlete_pk, x_person_pk, x_if_turn_id or x_if_job_id, x_pl_nested_operation == "true", x_if_generation_id, x_if_generation_attempt, x_pl_principal)
    return JSONResponse(result, status_code=202) if isinstance(result, dict) and ("job_id" in result or "generation_id" in result) and not result.get("cached") else result


@app.post("/mcp", dependencies=[Depends(authenticate)])
async def mcp(request: Request, x_athlete_pk: str = Header(default=""), x_person_pk: str = Header(default=""), x_pl_principal: str = Header(default="")):
    body = await request.json()
    method, request_id = body.get("method"), body.get("id")
    if request_id is None:
        return JSONResponse({}, status_code=202)
    result: dict[str, Any]
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": f"powerlifting-{DOMAIN}", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": op.name, "description": op.description, "inputSchema": op.input_schema, **({"outputSchema": JOB_SUBMITTED_SCHEMA if op.execution == "ai" else op.result_schema} if op.execution == "ai" or op.result_schema.get("type") == "object" else {})} for op in OPERATIONS.values() if not permission_map().get(op.name, {}).get("internal_only")]}
    elif method == "tools/call":
        params = body.get("params") or {}
        try:
            value = jsonable_encoder(await call(params.get("name", ""), params.get("arguments", {}), x_athlete_pk, x_person_pk, principal=x_pl_principal))
            result = {"content": [{"type": "text", "text": json.dumps(value)}], "isError": False}
            if isinstance(value, dict):
                result["structuredContent"] = value
        except HTTPException as exc:
            result = {"content": [{"type": "text", "text": json.dumps({"error": exc.detail, "status": exc.status_code})}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def openapi():
    return {"openapi": "3.1.0", "info": {"title": app.title, "version": "1.0.0"}, "paths": {f"/operations/{op.name}": {"post": {"operationId": op.name, "summary": op.description, "requestBody": {"required": True, "content": {"application/json": {"schema": op.input_schema}}}, "responses": {**({"202": {"description": "Queued execution", "content": {"application/json": {"schema": JOB_SUBMITTED_SCHEMA}}}} if op.execution == "ai" else {}), "200": {"description": "Domain result", "content": {"application/json": {"schema": op.result_schema}}}}, "security": [{"internal": []}]}} for op in OPERATIONS.values()}, "components": {"securitySchemes": {"internal": {"type": "apiKey", "in": "header", "name": "X-Internal-Token"}}}}


app.openapi = openapi


@app.post("/executions/{execution_id}", dependencies=[Depends(authenticate)])
async def resume(execution_id: str, arguments: dict[str, Any], x_athlete_pk: str = Header(default=""), x_if_job_id: str = Header(default=""), x_if_turn_id: str = Header(default=""), x_person_pk: str = Header(default=""), x_pl_principal: str = Header(default="")):
    try:
        active = execution.executions.get(execution_id)
        if active is None:
            raise OperationError(409, 'uncertain', 'Execution unavailable')
        claims, _ = await authorize_request('domain_resume', {'operation': active.operation}, x_pl_principal, x_person_pk, x_athlete_pk)
        if active.person != claims['sub'] or active.athlete != claims['athlete']:
            raise OperationError(403, 'forbidden', 'Execution belongs to another Person')
        return await execution.resume(execution_id, x_if_turn_id or x_if_job_id, x_athlete_pk, arguments.get("challenge_id"), arguments.get("content"))
    except OperationError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/generations/{generation_id}", dependencies=[Depends(authenticate)])
async def generation_status(generation_id: str, x_athlete_pk: str = Header(default=""), x_person_pk: str = Header(default=""), x_pl_principal: str = Header(default="")):
    from .generations import status
    if not x_athlete_pk:
        raise HTTPException(403, "Authenticated Athlete required")
    try:
        claims, access = await authorize_request('generation_status', {}, x_pl_principal, x_person_pk, x_athlete_pk)
        return await status(generation_id, claims['athlete'], claims['sub'], access)
    except OperationError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})


@app.post('/internal/access', dependencies=[Depends(authenticate)])
async def internal_access(arguments: dict[str, Any], x_pl_principal: str = Header(default='')):
    if DOMAIN != 'profile':
        raise HTTPException(404, 'Not found')
    try:
        _, context = await authorize_request(arguments.get('operation', ''), arguments.get('arguments') or {}, x_pl_principal, '', '')
        return context
    except OperationError as exc:
        raise HTTPException(exc.status, {'code': exc.code, 'message': exc.message})
