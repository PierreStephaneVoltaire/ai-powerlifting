import re

from .access_store import current_context, person_record
from .dispatch import OperationError

SERVED_MEDIA_PATH = re.compile(r'^/api/(?:budget|profiles|videos)/media/')


def stored_key(value):
    return SERVED_MEDIA_PATH.sub('', value) if isinstance(value, str) else ''


def handler(event, context):
    owner = person_record(event['pk'])
    key = event['s3_key']
    if not owner or stored_key(owner.get('avatar_url')) != key or not key.startswith('profiles/'):
        raise OperationError(404, 'not_found', 'Avatar not found')
    access = current_context(event.get('_person_pk', ''), owner.get('mapped_pk') or owner['pk'])
    if 'profile:read' not in access['permissions']:
        raise OperationError(404, 'not_found', 'Avatar not found')
    return {'s3_key': key}
