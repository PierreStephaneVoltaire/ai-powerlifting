import asyncio
import hmac
import json
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from jsonschema import ValidationError

from .contract import JOB_SUBMITTED_SCHEMA, load_operations
from .dispatch import OperationError, authorize, dispatch
from . import execution


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


async def call(name: str, arguments: dict[str, Any], athlete: str, person: str, job_id: str = "", nested_operation: bool = False, generation_id: str = "", generation_attempt: int = 0):
    if generation_id and not job_id:
        raise HTTPException(403, "Generation requires an active native turn")
    if name not in OPERATIONS:
        raise HTTPException(404, "Unknown operation")
    operation = OPERATIONS[name]
    try:
        arguments = authorize(operation, arguments, athlete, person)
        operation.validate_input(arguments)
        if job_id:
            arguments["_if_job_id"] = job_id
            if generation_id:
                arguments["_generation_id"] = generation_id
                arguments["_generation_attempt"] = generation_attempt
            arguments["_person_pk"] = person
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
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})
    except ValidationError as exc:
        raise HTTPException(422, {"code": "validation", "message": exc.message})
    except ValueError as exc:
        raise HTTPException(422, {"code": "validation", "message": str(exc)})


@app.post("/operations/{name}", dependencies=[Depends(authenticate)])
async def operation(name: str, arguments: dict[str, Any], x_athlete_pk: str = Header(default=""), x_person_pk: str = Header(default=""), x_if_job_id: str = Header(default=""), x_pl_nested_operation: str = Header(default=""), x_if_turn_id: str = Header(default=""), x_if_generation_id: str = Header(default=""), x_if_generation_attempt: int = Header(default=0)):
    result = await call(name, arguments, x_athlete_pk, x_person_pk, x_if_turn_id or x_if_job_id, x_pl_nested_operation == "true", x_if_generation_id, x_if_generation_attempt)
    return JSONResponse(result, status_code=202) if isinstance(result, dict) and ("job_id" in result or "generation_id" in result) and not result.get("cached") else result


@app.post("/mcp", dependencies=[Depends(authenticate)])
async def mcp(request: Request, x_athlete_pk: str = Header(default=""), x_person_pk: str = Header(default="")):
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
        result = {"tools": [{"name": op.name, "description": op.description, "inputSchema": op.input_schema, **({"outputSchema": JOB_SUBMITTED_SCHEMA if op.execution == "ai" else op.result_schema} if op.execution == "ai" or op.result_schema.get("type") == "object" else {})} for op in OPERATIONS.values()]}
    elif method == "tools/call":
        params = body.get("params") or {}
        try:
            value = await call(params.get("name", ""), params.get("arguments", {}), x_athlete_pk, x_person_pk)
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
async def resume(execution_id: str, arguments: dict[str, Any], x_athlete_pk: str = Header(default=""), x_if_job_id: str = Header(default=""), x_if_turn_id: str = Header(default="")):
    try:
        return await execution.resume(execution_id, x_if_turn_id or x_if_job_id, x_athlete_pk, arguments.get("challenge_id"), arguments.get("content"))
    except OperationError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/generations/{generation_id}", dependencies=[Depends(authenticate)])
async def generation_status(generation_id: str, x_athlete_pk: str = Header(default="")):
    from .generations import status
    if not x_athlete_pk:
        raise HTTPException(403, "Authenticated Athlete required")
    try:
        return await status(generation_id, x_athlete_pk)
    except OperationError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message})
