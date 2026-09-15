import asyncio
import os

import httpx

from .access import operation_permission, permission_map, permits
from .access_store import current_context
from .dispatch import OperationError
from .principal import verify_principal
from .media_access import additional_permission
from .competition_access import authorize_entry
from .program_access import authorize_program_change
from .source_access import authorize_source


def check_context(operation: str, arguments: dict, claims: dict, context: dict) -> dict:
    rule = permission_map().get(operation)
    if not rule:
        raise OperationError(403, 'forbidden', 'Operation has no permission mapping')
    if rule.get('internal_only') and claims['iss'] != 'powerlifting-gateway':
        raise OperationError(403, 'forbidden', 'Operation is internal to the gateway')
    if operation == 'identity_resolve':
        identity = claims.get('identity') or {}
        if not identity or any(arguments.get(key) != identity.get(key) for key in ('issuer', 'provider', 'sub')):
            raise OperationError(403, 'forbidden', 'Verified identity does not match the request')
        if arguments.get('discord_subjects', []) != identity.get('discord_subjects', []):
            raise OperationError(403, 'forbidden', 'Linked subjects are not verified')
        return context
    if operation == 'access_context' or rule.get('public'):
        return context
    if not permits(context, operation_permission(operation, arguments)):
        raise OperationError(403, 'forbidden', 'Not permitted')
    if '_required_access' in arguments:
        authorize_source(arguments['_required_access'], context)
    authorize_entry(operation, arguments, operation_permission(operation, arguments), context)
    authorize_program_change(operation, arguments, context)
    media_permission = additional_permission(operation, arguments, claims.get('athlete', ''))
    if media_permission and not permits(context, media_permission):
        raise OperationError(403, 'forbidden', f'{media_permission} permission required')
    return context


async def authorize_request(operation: str, arguments: dict, token: str, person: str, athlete: str) -> tuple[dict, dict]:
    try:
        claims = verify_principal(token, operation, person, athlete)
    except Exception as exc:
        raise OperationError(401, 'invalid_principal', 'Verified acting Person required') from exc
    if os.getenv('PL_DOMAIN') == 'profile':
        context = await asyncio.to_thread(current_context, claims['sub'], claims['athlete'])
        return claims, check_context(operation, arguments, claims, context)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(os.getenv('PL_PROFILE_URL', 'http://pl-profile.if-portals.svc.cluster.local:8000') + '/internal/access',
                headers={'X-Internal-Token': os.environ['INTERNAL_API_TOKEN'], 'X-PL-Principal': token},
                json={'operation': operation, 'arguments': arguments})
        if response.status_code != 200:
            raise OperationError(response.status_code, 'forbidden', 'Access evaluation denied')
        return claims, response.json()
    except httpx.HTTPError as exc:
        raise OperationError(503, 'access_unavailable', 'Permission service unavailable') from exc
