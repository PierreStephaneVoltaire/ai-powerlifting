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
                details = {key: result[key] for key in ('current_revision', 'current_record') if key in result}
                raise OperationError(status, result.get('code', 'operation_failed'), str(message), **details)
            raise OperationError(status, 'operation_failed', str(result))
    return result


def owner_aliases(arguments: dict[str, Any]) -> frozenset[str]:
    access = arguments.get('_access') or {}
    person = str(arguments.get('_person_pk') or access.get('person_pk') or '')
    if not person:
        return frozenset()
    return frozenset(value for value in (person, str(access.get('settings_pk') or ''), str(access.get('own_athlete_pk') or '')) if value)


def dispatch(operation: Operation, arguments: dict[str, Any]) -> Any:
    operation.validate_input({key: value for key, value in arguments.items() if not key.startswith("_")})
    if operation.handler is None:
        raise OperationError(501, "not_served", f"{operation.name} is served by a native service")
    from services.runtime.storage_scope import current_athlete, current_owner_aliases, current_person
    token = current_athlete.set(arguments.get("pk") if operation.ownership != "public" else None)
    person_token = current_person.set(arguments.get("_person_pk"))
    aliases_token = current_owner_aliases.set(owner_aliases(arguments))
    try:
        module = importlib.import_module(operation.handler)
        result = unwrap(module.handler(arguments, None))
    finally:
        current_person.reset(person_token)
        current_owner_aliases.reset(aliases_token)
        current_athlete.reset(token)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass
    from .publication import operation_result
    result = operation_result(operation.name, result, arguments.get('_access'))
    try:
        operation.validate_result(result)
    except Exception as exc:
        raise OperationError(500, "invalid_result", "Domain returned an invalid result") from exc
    from .analysis_version import record_write
    access = arguments.get("_access") or {}
    record_write(operation.name, access.get("athlete_pk") or access.get("own_athlete_pk"))
    return result
