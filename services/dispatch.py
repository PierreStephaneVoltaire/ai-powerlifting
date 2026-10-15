import importlib
import json
import os
from decimal import Decimal
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
    if operation.name == "identity_resolve":
        return dict(arguments)
    if operation.ownership != "public" and not athlete:
        raise OperationError(403, "forbidden", "Athlete scope required")
    if operation.ownership == "operator" and 'operator:write' not in (access or {}).get('permissions', []):
        raise OperationError(403, "forbidden", "Operator permission required")
    scoped = dict(arguments)
    if scoped.get('actor_pk') and scoped['actor_pk'] != person:
        raise OperationError(403, 'forbidden', 'Acting Person differs from authenticated identity')
    if 'actor_pk' in scoped:
        scoped['actor_pk'] = person
    settings_pk = (access or {}).get('settings_pk', '')
    if scoped.get('viewer_username') and scoped['viewer_username'] != settings_pk:
        raise OperationError(403, 'forbidden', 'Viewer differs from authenticated Person')
    if 'viewer_username' in operation.input_schema.get('properties', {}):
        if settings_pk:
            scoped['viewer_username'] = settings_pk
        else:
            scoped.pop('viewer_username', None)
    if operation.ownership == 'person' and not operation.name.startswith('grant_'):
        if not person or not settings_pk:
            raise OperationError(403, 'forbidden', 'Authenticated Person required')
        if any(scoped.get(key) for key in ('identity_provider', 'identity_sub', 'identity_issuer', 'discord_id', 'authentik_sub')):
            raise OperationError(403, 'forbidden', 'Identity selectors are not settings selectors')
        for key in ('username', 'discord_username', 'mapped_pk', 'pk'):
            if scoped.get(key) and scoped[key] not in {settings_pk, person, (access or {}).get('own_athlete_pk')}:
                raise OperationError(403, 'forbidden', 'Person selector conflicts with authenticated identity')
        if 'username' in operation.input_schema.get('properties', {}):
            scoped['username'] = settings_pk
        if 'mapped_pk' in scoped:
            scoped['mapped_pk'] = (access or {}).get('own_athlete_pk')
        scoped['pk'] = settings_pk
        return scoped
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
    from services.lib.storage_scope import current_athlete, current_owner_aliases
    token = current_athlete.set(arguments.get("pk") if operation.ownership != "public" else None)
    aliases_token = current_owner_aliases.set(owner_aliases(arguments))
    try:
        module = importlib.import_module(operation.handler)
        result = unwrap(module.handler(arguments, None))
    finally:
        current_owner_aliases.reset(aliases_token)
        current_athlete.reset(token)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass
    if operation.name.startswith('settings_') and isinstance(result, dict) and 'tags' in result:
        from .tag_catalog import selected_tags
        result['tags'] = selected_tags(result['tags'])
    if operation.name == 'identity_resolve':
        from .tag_catalog import selected_tags
        result['settings']['tags'] = selected_tags(result['settings'].get('tags'))
    if operation.name in ('profile_get', 'profile_get_current', 'profile_search'):
        from .tag_catalog import selected_tags
        for profile in result.get('profiles', []) if operation.name == 'profile_search' else [result]:
            profile['tags'] = [tag['tag'] for tag in selected_tags(profile.get('tags')) if tag['approved']]
    from .publication import operation_result
    result = operation_result(operation.name, result, arguments.get('_access'))
    try:
        operation.validate_result(result)
    except Exception as exc:
        raise OperationError(500, "invalid_result", "Domain returned an invalid result") from exc
    return result
