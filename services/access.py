import json
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import casbin


DOMAINS = ('profile', 'program', 'sessions', 'competition', 'federation', 'glossary', 'goals', 'budget', 'calculations', 'performance', 'weight-log', 'templates', 'imports', 'lift-profiles', 'analytics', 'videos')
COACH_PERMISSIONS = [f'{domain}:{action}' for domain in DOMAINS for action in ('read', 'write')]
HANDLER_PERMISSIONS = [f'{domain}:read' for domain in ('profile', 'program', 'sessions', 'competition', 'budget', 'performance', 'lift-profiles', 'videos', 'calculations')] + ['competition:write']
PROGRAM_FIELDS = {'phases': 'program', 'diet_notes': 'program', 'supplements': 'program', 'supplement_phases': 'program', 'sessions': 'sessions', 'competitions': 'competition', 'competition': 'competition', 'lift_profiles': 'lift-profiles', 'current_maxes': 'performance', 'goals': 'goals', 'weight_log': 'weight-log', 'max_history': 'performance', 'federation_library': 'federation'}
META_DOMAINS = {
    'competition': ('comp_date', 'practicing_for', 'weight_class_kg', 'weight_class_confirm_by', 'last_comp', 'attempt_pct', 'lift_attempt_settings'),
    'weight-log': ('current_body_weight_kg', 'current_body_weight_lb', 'height_cm', 'arm_wingspan_cm', 'leg_length_cm'),
    'performance': ('target_squat_kg', 'target_bench_kg', 'target_dl_kg', 'target_total_kg', 'manual_maxes', 'block_start_maxes'),
    'federation': ('federation',),
}


@lru_cache(maxsize=1)
def permission_map() -> dict:
    return json.loads((Path(__file__).parent / 'permissions.json').read_text())


def operation_permission(name: str, arguments: dict) -> str | None:
    if name == 'health_list_competitions':
        operation = arguments.get('op')
        if not operation:
            operation = 'update' if arguments.get('master_id') and arguments.get('patch') is not None else 'complete' if arguments.get('master_id') and arguments.get('results') is not None else 'list'
        return 'competition:read' if operation == 'list' else 'competition:write' if operation in ('update', 'complete') else None
    if name in ('note_list_attachments', 'note_share'):
        domain = arguments.get('context_domain')
        return f"{domain}:{'read' if name == 'note_list_attachments' else 'write'}" if domain in ('program', 'sessions', 'competition') else None
    if name == 'domain_resume':
        resumed = arguments.get('operation')
        if resumed in ('domain_resume', 'generation_status'):
            return None
        return operation_permission(resumed, {})
    rule = permission_map().get(name)
    if not rule:
        return None
    cache_only = arguments.get('cache_only') is True or arguments.get('cacheOnly') is True
    if cache_only and arguments.get('refresh') is not True:
        return rule.get('cache_read', rule['permission'])
    return rule['permission']


def grant_permissions(grant: dict, competition_dates: dict, now: datetime) -> list[str]:
    if grant.get('revoked_at') or grant.get('state', 'approved') != 'approved':
        return []
    role = grant.get('grant_type') or grant.get('kind')
    if role in ('coach', 'handler'):
        tied = grant.get('tied_competition_ids') or []
        if not tied or any(key not in competition_dates for key in tied):
            return []
        try:
            expires = datetime.combine(max(date.fromisoformat(competition_dates[key][:10]) for key in tied) + timedelta(days=7), time.max, timezone.utc)
        except (ValueError, TypeError):
            return []
        if now > expires:
            return []
    elif role in ('peer', 'read'):
        if grant.get('expires_at'):
            try:
                if now >= datetime.fromisoformat(grant['expires_at'].replace('Z', '+00:00')):
                    return []
            except (ValueError, TypeError):
                return []
    else:
        return []
    permissions = grant.get('permissions')
    if permissions is None:
        permissions = COACH_PERMISSIONS if role == 'coach' else HANDLER_PERMISSIONS if role == 'handler' else ['profile:read']
        if grant.get('scope') == 'read':
            permissions = [permission for permission in permissions if permission.endswith(':read')]
    if not isinstance(permissions, list):
        return []
    valid = set(COACH_PERMISSIONS)
    return [permission for permission in permissions if permission in valid and (role not in ('peer', 'read') or permission.endswith(':read'))]


def active_grants(grants: list[dict], competition_dates: dict, now: datetime) -> list[dict]:
    slots = {str(item.get('grant_type')): item for item in grants if item.get('entity') == 'relationship_slot' or str(item.get('sk', '')).startswith('RelationshipSlot#')}
    candidates = [grant for grant in grants if grant_permissions(grant, competition_dates, now)]
    result = []
    for grant in candidates:
        role = grant.get('grant_type') or grant.get('kind')
        if role in ('coach', 'handler'):
            slot = slots.get(role)
            if slot:
                if slot.get('state') != 'active' or slot.get('relationship_id') != grant.get('relationship_id'):
                    continue
            elif sum((other.get('grant_type') or other.get('kind')) == role for other in candidates) > 1:
                continue
        result.append(grant)
    return result


def evaluate_facts(person: str, athlete: str, owner: dict | None, actor: dict | None, grants: list[dict], competition_dates: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    permissions = {'calculations:read', 'federation:read'}
    granted_permissions = set()
    own_athlete = str((actor or {}).get('mapped_pk') or (actor or {}).get('pk') or '')
    is_self = bool(person and actor and owner and own_athlete == athlete)
    competition_scope = {'read': None if is_self else set(), 'write': None if is_self else set()}
    if actor:
        permissions.update(['settings:read', 'settings:write'])
    if is_self:
        permissions.update(['profile:read', 'profile:write'])
    if is_self and 'athlete' in actor.get('roles', []):
        from importlib import import_module
        status = import_module('services.handlers.user._shared.settings_normalize').derive_onboarding_status(actor)
        permissions.update(['grants:read', 'grants:write'])
        if status['has_athlete_basics']:
            permissions.update(COACH_PERMISSIONS)
    if owner and owner.get('profile_visibility') == 'public':
        permissions.add('profile:read')
        for domain in (owner.get('publication') or {}).get('domains', []):
            if domain in DOMAINS:
                permissions.add(f'{domain}:read')
                if domain == 'competition':
                    competition_scope['read'] = None
    if actor:
        actor_ids = {person, str(actor.get('pk') or ''), own_athlete}
        for grant in active_grants(grants, competition_dates, now):
            if grant.get('grantee_mapped_pk') in actor_ids or grant.get('grantee_person_pk') == person:
                effective = grant_permissions(grant, competition_dates, now)
                granted_permissions.update(effective)
                for action in ('read', 'write'):
                    if f'competition:{action}' not in effective or competition_scope[action] is None:
                        continue
                    if (grant.get('grant_type') or grant.get('kind')) in ('peer', 'read'):
                        competition_scope[action] = None
                    else:
                        competition_scope[action].update(grant.get('tied_competition_ids') or [])
        permissions.update(granted_permissions)
    if actor and own_athlete == 'operator':
        permissions.update(['operator:read', 'operator:write'])
    return {'person_pk': person, 'athlete_pk': athlete, 'own_athlete_pk': own_athlete, 'settings_pk': str((actor or {}).get('pk') or ''), 'is_self': is_self, 'permissions': sorted(permissions), 'granted_permissions': sorted(granted_permissions), 'competition_scope': {action: sorted(ids) if ids is not None else None for action, ids in competition_scope.items()}}


def permits(context: dict, permission: str | None) -> bool:
    if not permission:
        return False
    model = casbin.Model()
    model.load_model_from_text('[request_definition]\nr = permission\n[policy_definition]\np = permission\n[policy_effect]\ne = some(where (p.eft == allow))\n[matchers]\nm = r.permission == p.permission')
    enforcer = casbin.Enforcer(model)
    for effective in context['permissions']:
        enforcer.add_policy(effective)
    return enforcer.enforce(permission)
