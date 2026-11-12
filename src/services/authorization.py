from .access import operation_permission, permission_map, permits
from .mesh import BACKEND_ACCOUNT, is_account
from .dispatch import OperationError
from .media_access import additional_permission
from .competition_access import authorize_entry
from .program_access import authorize_program_change
from .source_access import authorize_source


def check_context(operation: str, arguments: dict, claims: dict, context: dict) -> dict:
    rule = permission_map().get(operation)
    if not rule:
        raise OperationError(403, 'forbidden', 'Operation has no permission mapping')
    if rule.get('internal_only') and not is_account(claims.get('caller', ''), BACKEND_ACCOUNT):
        raise OperationError(403, 'forbidden', 'Operation is internal to the gateway')
    if operation in ('identity_resolve', 'access_context') or rule.get('public'):
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

