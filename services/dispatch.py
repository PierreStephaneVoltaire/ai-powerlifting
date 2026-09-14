import importlib
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from .contract import Operation
from .access import permission_map


ROOT = Path(__file__).resolve().parent.parent
for directory in [ROOT, *(ROOT / "lambda/layers").glob("*/python"), *(ROOT / "lambda/layers").glob("*/content")]:
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


class OperationError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def authorize(operation: Operation, arguments: dict[str, Any], athlete: str, person: str) -> dict[str, Any]:
    if operation.name not in permission_map():
        raise OperationError(403, "forbidden", "Operation has no permission mapping")
    if operation.ownership != "public" and not athlete:
        raise OperationError(403, "forbidden", "Athlete scope required")
    if operation.ownership == "operator" and person != "operator":
        raise OperationError(403, "forbidden", "Operator permission required")
    scoped = dict(arguments)
    if operation.name.startswith("grant_"):
        if not person:
            raise OperationError(403, "forbidden", "Person scope required")
        target = arguments.get("athlete_mapped_pk")
        if target and target != athlete:
            raise OperationError(403, "forbidden", "Grant target differs from authenticated Athlete")
        if operation.name == "grant_check" and arguments.get("actor_mapped_pk") != person:
            raise OperationError(403, "forbidden", "Grant check actor differs from authenticated Person")
        if operation.name == "grant_list" and not target and arguments.get("grantee_mapped_pk") != person:
            raise OperationError(403, "forbidden", "Grants may only be listed for the authenticated Person")
        if operation.name in {"grant_create", "grant_revoke"}:
            scoped["created_by" if operation.name == "grant_create" else "revoked_by"] = person

    for key in ("pk", "user_pk", "mapped_pk", "_user_pk", "actor_pk"):
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
            message = result.get("error", "Operation failed") if isinstance(result, dict) else str(result)
            raise OperationError(status, "operation_failed", str(message))
    return result


def dispatch(operation: Operation, arguments: dict[str, Any]) -> Any:
    operation.validate_input({key: value for key, value in arguments.items() if not key.startswith("_")})
    package_root = ROOT / "lambda" / operation.handler.split(".")[1] / "handlers"
    if package_root.is_dir() and str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from storage_scope import current_athlete
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
