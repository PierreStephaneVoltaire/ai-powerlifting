import base64
import hashlib
import importlib
import json
import os

from .access_store import current_context, database, pages, person_record
from .dispatch import OperationError
from .tag_catalog import catalog, normalize_tag, selected_tags


def people():
    return [item for item in pages(database().Table(os.getenv('IF_USER_TABLE', 'if-user')), 'scan', ConsistentRead=True) if not str(item.get('pk', '')).startswith('Identity#')]


def visible_profile(owner, actor, vocabulary, details=False):
    athlete = str(owner.get('mapped_pk') or owner['pk'])
    access = current_context(actor, athlete)
    allowed = set(access['permissions'])
    if 'profile:read' not in allowed:
        return None
    private = access['is_self'] or 'profile:read' in access.get('granted_permissions', [])
    federations = [value for value in owner.get('federations', []) if isinstance(value, str)]
    result = {
        'athlete_pk': athlete,
        'nickname': owner.get('nickname') or owner.get('username') or owner['pk'],
        'display_name': owner.get('display_name') or owner.get('nickname') or owner['pk'],
        'avatar_url': owner.get('avatar_url'),
        'bio': owner.get('bio', '') if private else '',
        'profile_visibility': 'public' if owner.get('profile_visibility') == 'public' else 'private',
        'public_training_summary_enabled': 'analytics:read' in allowed,
        'is_self': access['is_self'],
        'roles': owner.get('roles', ['athlete']),
        'federations': federations,
        'tags': [tag['tag'] for tag in selected_tags(owner.get('tags'), vocabulary) if tag['approved']],
        'federation': federations[0] if federations else None,
        'weight_class_kg': None,
        'practicing_for': None,
        'summary': dict.fromkeys(['squat_kg', 'bench_kg', 'deadlift_kg', 'total_kg', 'bodyweight_kg', 'dots']),
        'lift_videos': [],
    }
    if details and allowed.intersection({'performance:read', 'sessions:read', 'competition:read', 'lift-profiles:read'}):
        legacy = importlib.import_module('services.handlers.user.profile_get.core')
        health = database().Table(os.getenv('IF_HEALTH_TABLE_NAME', 'if-health'))
        program_sk = legacy._resolve_program_sk_sync(health, athlete)
        program = legacy._load_program_sync(health, athlete, program_sk)
        if program and program.get('published', True):
            from services.lib.session_store import SessionStore
            sessions = SessionStore(os.getenv('IF_SESSIONS_TABLE_NAME', 'if-sessions'), pk=athlete, region=os.getenv('AWS_REGION', 'ca-central-1')).list_sessions_sync(program_sk, program.get('phases', [])) if 'sessions:read' in allowed or 'performance:read' in allowed else []
            derived = legacy._build_profile(owner, None, program, sessions)
            if 'performance:read' in allowed:
                result['summary'] = derived['summary']
            if 'weight-log:read' not in allowed:
                result['summary'].update(bodyweight_kg=None, dots=None)
            if 'competition:read' in allowed:
                result.update(weight_class_kg=derived['weight_class_kg'], practicing_for=derived['practicing_for'])
            if {'sessions:read', 'videos:read'} <= allowed:
                result['lift_videos'] = [{**item, 'athlete_pk': athlete} for item in derived['lift_videos']]
            if 'lift-profiles:read' in allowed:
                from .publication import program_view
                result['lift_profiles'] = program_view(program, access).get('lift_profiles', [])
    return result


def get_by_handle(args):
    matches = [item for item in people() if (item.get('nickname') or item.get('username') or item['pk']).lower() == args['nickname'].lower()]
    profile = visible_profile(matches[0], args.get('_person_pk', ''), catalog(), details=True) if len(matches) == 1 else None
    if profile is None:
        raise OperationError(404, 'not_found', 'Profile not found')
    return profile


def get_current(args):
    owner = person_record(args['pk'])
    profile = visible_profile(owner, args.get('_person_pk', ''), catalog(), details=True) if owner else None
    if profile is None:
        raise OperationError(404, 'not_found', 'Profile not found')
    return profile


def search(args):
    query = args.get('query', '').strip().casefold()
    federation_filter = set(args.get('federations', []))
    requested_tags = {normalize_tag(tag) for tag in args.get('tags', [])}
    mode = args.get('tag_mode', 'and')
    role = args.get('role')
    vocabulary = catalog()
    if any(vocabulary.get(tag, {}).get('status') != 'approved' for tag in requested_tags):
        return {'profiles': [], 'next_cursor': None}
    fingerprint = hashlib.sha256(json.dumps([query, sorted(federation_filter), sorted(requested_tags), mode, role]).encode()).hexdigest()
    after = None
    if args.get('cursor'):
        try:
            cursor = json.loads(base64.urlsafe_b64decode(args['cursor'] + '=' * (-len(args['cursor']) % 4)))
            if cursor['filter'] != fingerprint or not isinstance(cursor['after'], list) or len(cursor['after']) != 2 or any(not isinstance(value, str) for value in cursor['after']):
                raise ValueError()
            after = tuple(cursor['after'])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('Invalid search cursor') from exc
    found = []
    for owner in people():
        roles = owner.get('roles', ['athlete'])
        if role and role not in roles:
            continue
        if owner.get('profile_visibility') == 'public' and not {'athlete', 'coach'}.intersection(roles):
            continue
        handle = owner.get('nickname') or owner.get('username') or owner['pk']
        display = owner.get('display_name') or handle
        key = (display.casefold(), handle)
        if after and key <= after:
            continue
        if query and query not in display.casefold() and query not in handle.casefold():
            continue
        if federation_filter and not federation_filter.intersection(owner.get('federations', [])):
            continue
        approved = {tag['tag'] for tag in selected_tags(owner.get('tags'), vocabulary) if tag['approved']}
        if requested_tags and not (requested_tags <= approved if mode == 'and' else requested_tags.intersection(approved)):
            continue
        profile = visible_profile(owner, args.get('_person_pk', ''), vocabulary)
        if profile:
            found.append((key, profile))
    found.sort(key=lambda pair: pair[0])
    page = found[:20]
    next_cursor = base64.urlsafe_b64encode(json.dumps({'filter': fingerprint, 'after': page[-1][0]}).encode()).decode().rstrip('=') if len(found) > 20 else None
    return {'profiles': [profile for _, profile in page], 'next_cursor': next_cursor}
