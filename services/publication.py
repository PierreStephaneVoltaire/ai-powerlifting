import copy
import os
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from .access import DOMAINS, META_DOMAINS, PROGRAM_FIELDS
from .access_store import database
from .dispatch import OperationError


def _public_publication(value):
    return {'domains': list(value.get('domains') or []), 'revision': int(value.get('revision', 0))}


def handler(args, _context):
    person = args['_access']['settings_pk']
    table = database().Table(os.getenv('IF_USER_TABLE', 'if-user'))
    owner = table.get_item(Key={'pk': person}, ConsistentRead=True).get('Item')
    if not owner:
        raise OperationError(404, 'not_found', 'Profile not found')
    current = owner.get('publication') or {'domains': [], 'revision': 0}
    if args.get('domains') is None:
        return _public_publication(current)
    if 'athlete' not in owner.get('roles', []):
        raise OperationError(403, 'forbidden', 'Only Athletes publish training domains')
    domains = sorted(set(args['domains']))
    if any(domain not in DOMAINS for domain in domains):
        raise ValueError('Unknown publication domain')
    if current.get('idempotency_key') == args['idempotency_key']:
        if current['domains'] != domains:
            raise OperationError(409, 'conflict', 'This publication key was already used')
        return _public_publication(current)
    revision = int(current.get('revision', 0))
    if args['expected_revision'] != revision:
        raise OperationError(409, 'conflict', 'Publication changed', current_revision=revision, current_record=_public_publication(current))
    result = {'domains': domains, 'revision': revision + 1, 'idempotency_key': args['idempotency_key'], 'updated_at': datetime.now(timezone.utc).isoformat()}
    try:
        table.update_item(Key={'pk': person}, UpdateExpression='SET publication = :publication', ConditionExpression='attribute_exists(pk) AND (attribute_not_exists(publication) OR publication.revision = :expected)', ExpressionAttributeValues={':publication': result, ':expected': revision})
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise
        raise OperationError(409, 'conflict', 'Publication changed; reload it') from exc
    return _public_publication(result)


def session_view(session, access):
    out = copy.deepcopy(session)
    permissions = set(access.get('permissions', []))
    if 'videos:read' not in permissions:
        out.pop('videos', None)
    if 'weight-log:read' not in permissions:
        out.pop('body_weight_kg', None)
        out.pop('body_weight_lb', None)
    return out


def program_view(program, access):
    from .competition_access import visible_entries
    out = copy.deepcopy(program)
    permissions = set(access.get('permissions', []))
    for field, domain in PROGRAM_FIELDS.items():
        if f'{domain}:read' not in permissions:
            out[field] = [] if isinstance(out.get(field), list) else {}
    if isinstance(out.get('sessions'), list):
        out['sessions'] = [session_view(session, access) for session in out['sessions']]
    if isinstance(out.get('competitions'), list):
        out['competitions'] = visible_entries(out['competitions'], access)
    if 'videos:read' not in permissions:
        for profile in out.get('lift_profiles') or []:
            if isinstance(profile, dict):
                profile.pop('form_videos', None)
    meta = out.get('meta') or {}
    if 'program:read' not in permissions:
        names = {name for domain, fields in META_DOMAINS.items() if f'{domain}:read' in permissions for name in fields}
        meta = {name: value for name, value in meta.items() if name in names}
    for domain, names in META_DOMAINS.items():
        if f'{domain}:read' not in permissions:
            for name in names:
                meta.pop(name, None)
    if 'performance:read' not in permissions:
        for block in meta.get('blocks', []):
            block.pop('start_maxes_kg', None)
    out['meta'] = meta
    return out


def operation_result(name, value, access):
    access = access or {}
    if access and access.get('is_self'):
        return value
    if name == 'health_list_competitions':
        from .competition_access import visible_entries
        if isinstance(value, list):
            return visible_entries(value, access)
        if isinstance(value, dict) and isinstance(value.get('competitions'), list):
            return {**value, 'competitions': visible_entries(value['competitions'], access)}
    if name in ('program_get', 'health_get_program'):
        return program_view(value, access)
    if name == 'program_list_full':
        if isinstance(value, list):
            return [program_view(item, access) for item in value]
        return {**value, 'programs': [program_view(item, access) for item in value.get('programs', [])]}
    if name in ('health_get_meta',):
        return program_view({'meta': value}, access)['meta']
    if name in ('program_update_meta_field', 'health_update_meta') and isinstance(value, dict):
        return {**value, 'meta': program_view({'meta': value.get('meta') or {}}, access)['meta']}
    if name == 'block_transition' and isinstance(value, dict) and isinstance(value.get('program'), dict):
        return {**value, 'program': program_view(value['program'], access)}
    if name == 'health_update_session' and isinstance(value, dict):
        return program_view(value, access)
    if name in ('session_get', 'health_get_session'):
        return session_view(value, access)
    if name in ('session_list', 'session_list_full', 'health_get_sessions_range'):
        if isinstance(value, list):
            return [session_view(item, access) for item in value]
        return {**value, 'sessions': [session_view(item, access) for item in value.get('sessions', [])]}
    return value
