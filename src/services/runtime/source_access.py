from .dispatch import OperationError
from .access import DOMAINS


def read_requirements(context: dict) -> dict:
    return {
        'permissions': sorted(permission for permission in context.get('permissions', []) if permission.endswith(':read') and permission.split(':')[0] in DOMAINS),
        'competition_ids': context.get('competition_scope', {}).get('read', []),
    }


def authorize_source(requirements: dict | None, context: dict) -> None:
    if requirements is None:
        if context.get('is_self'):
            return
        raise OperationError(403, 'forbidden', 'This saved result needs to be regenerated with current access')
    if not set(requirements.get('permissions', [])).issubset(context.get('permissions', [])):
        raise OperationError(403, 'forbidden', 'Access to this saved result has changed')
    if 'competition:read' in requirements.get('permissions', []):
        current = context.get('competition_scope', {}).get('read', [])
        required = requirements.get('competition_ids')
        if current is not None and (required is None or not {value.removeprefix('COMP#') for value in required}.issubset(value.removeprefix('COMP#') for value in current)):
            raise OperationError(403, 'forbidden', 'This saved result includes Competition Entries outside the current grant')
