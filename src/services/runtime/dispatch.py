import importlib
import json
from typing import Any

from .contract import Operation
from .access import permission_map


class OperationError(Exception):
    def __init__(self, status: int, code: str, message: str, **details):
        self.status, self.code, self.message = status, code, message
        self.details = details
        super().__init__(message)


def authorize(operation: Operation, arguments: dict[str, Any], athlete: str, person: str, access: dict | None = None) -> dict[str, Any]:
    if operation.name not in permission_map():
        raise OperationError(403, "forbidden", "Operation has no permission mapping")
    if operation.ownership != "public" and not athlete:
        raise OperationError(403, "forbidden", "Athlete scope required")
    if operation.ownership == "operator" and 'operator:write' not in (access or {}).get('permissions', []):
        raise OperationError(403, "forbidden", "Operator permission required")
    scoped = dict(arguments)
    if scoped.get('actor_pk') and scoped['actor_pk'] != person:
        raise OperationError(403, 'forbidden', 'Acting Person differs from authenticated identity')
    if 'actor_pk' in scoped:
        scoped['actor_pk'] = person
    for key in ("pk", "user_pk", "mapped_pk", "_user_pk"):
        if key in scoped and scoped[key] and scoped[key] != athlete:
            raise OperationError(403, "forbidden", "Operation ownership conflicts with authenticated scope")
    if operation.ownership != "public":
        scoped["pk"] = athlete
    return scoped


def unwrap(result: Any) -> Any:
    if isinstance(result, dict) and "statusCode" in result:
        status = int(result["statusCode"])
        result = result.get("body")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass
        if status >= 400:
            if isinstance(result, dict):
                message = result.get('message') or result.get('error') or 'Operation failed'
                raise OperationError(status, result.get('code', 'operation_failed'), str(message))
            raise OperationError(status, 'operation_failed', str(result))
    return result


def dispatch(operation: Operation, arguments: dict[str, Any]) -> Any:
    operation.validate_input({key: value for key, value in arguments.items() if not key.startswith("_")})
    if operation.handler is None:
        raise OperationError(501, "not_served", f"{operation.name} is served by a native service")
    from services.runtime.storage_scope import current_athlete
    token = current_athlete.set(arguments.get("pk") if operation.ownership != "public" else None)
    try:
        module = importlib.import_module(operation.handler)
        result = unwrap(module.handler(arguments, None))
    finally:
        current_athlete.reset(token)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass
    try:
        operation.validate_result(result)
    except Exception as exc:
        raise OperationError(500, "invalid_result", "Domain returned an invalid result") from exc
    return result
