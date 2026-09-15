from .access_store import current_context, person_record
from .dispatch import OperationError


def handler(event, context):
    owner = person_record(event['pk'])
    key = event['s3_key']
    if not owner or owner.get('avatar_url') != key or not key.startswith('profiles/'):
        raise OperationError(404, 'not_found', 'Avatar not found')
    access = current_context(event.get('_person_pk', ''), owner.get('mapped_pk') or owner['pk'])
    if 'profile:read' not in access['permissions']:
        raise OperationError(404, 'not_found', 'Avatar not found')
    return {'s3_key': key}
