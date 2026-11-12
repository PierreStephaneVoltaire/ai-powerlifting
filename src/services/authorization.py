from .access import operation_permission, permission_map, permits
from .dispatch import OperationError
from .media_access import additional_permission
from .competition_access import authorize_entry
from .program_access import authorize_program_change
from .source_access import authorize_source


def check_context(operation: str, arguments: dict, claims: dict, context: dict) -> dict:
    rule = permission_map().get(operation)
    if not rule:
        raise OperationError(403, 'forbidden', 'Operation has no permission mapping')
    if rule.get('internal_only') and not (claims['iss'] == 'pl-security' and claims.get('origin') == 'pl-backend'):
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

