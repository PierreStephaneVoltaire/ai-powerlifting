from datetime import datetime, timezone

from services.runtime.access import evaluate_facts, permits, operation_permission, permission_map
from services.runtime.contract import load_operations


def test_current_grants_publication_and_person_ownership():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    owner = {'pk': 'owner', 'mapped_pk': 'athlete-a', 'roles': ['athlete'], 'sex': 'female', 'bodyweight_kg': 75, 'training_maxes': {'squat_kg': 150, 'bench_kg': 100, 'deadlift_kg': 200}}
    coach = {'pk': 'coach', 'roles': ['coach']}
    grant = {'grantee_mapped_pk': 'coach', 'grant_type': 'coach', 'tied_competition_ids': ['meet']}
    context = lambda grants, dates: evaluate_facts('coach', 'athlete-a', owner, coach, grants, dates, now)
    assert not permits(context([], {}), 'sessions:read')
    assert permits(context([grant], {'meet': '2026-09-14'}), 'sessions:write')
    assert not permits(context([grant], {'meet': '2026-08-01'}), 'sessions:read')
    assert not permits(context([{**grant, 'revoked_at': 'now'}], {'meet': '2026-09-14'}), 'sessions:read')
    assert not permits(context([grant], {}), 'sessions:read')
    assert not permits(context([grant], {'meet': '2026-09-14'}), 'grants:write')
    handler = {**grant, 'grant_type': 'handler'}
    assert permits(context([handler], {'meet': '2026-09-14'}), 'competition:write')
    assert not permits(context([handler], {'meet': '2026-09-14'}), 'sessions:write')
    assert permits(evaluate_facts('owner', 'athlete-a', owner, owner, [], {}, now), 'sessions:write')
    assert not permits(evaluate_facts('owner', 'athlete-a', owner, {**owner, 'sex': None}, [], {}, now), 'sessions:write')
    assert not permits(evaluate_facts('athlete-a', 'athlete-a', owner, None, [], {}, now), 'sessions:write')
    public = {**owner, 'profile_visibility': 'public', 'publication': {'domains': ['sessions']}}
    anonymous = evaluate_facts('', 'athlete-a', public, None, [], {}, now)
    assert permits(anonymous, 'profile:read') and permits(anonymous, 'sessions:read')
    assert not permits(anonymous, 'sessions:write') and not permits(anonymous, 'settings:read')


def test_every_operation_has_an_explicit_permission_and_generating_requires_write():
    assert set(load_operations()) <= permission_map().keys()
    assert operation_permission('unknown', {}) is None
    assert operation_permission('program_evaluation', {}) == 'analytics:write'
    assert operation_permission('program_evaluation', {'cache_only': True}) == 'analytics:read'
    assert operation_permission('program_evaluation', {'cache_only': True, 'refresh': True}) == 'analytics:write'
    assert operation_permission('analytics.blocks_get', {'cacheOnly': True}) == 'analytics:read'
    assert operation_permission('analytics.blocks_get', {'cacheOnly': True, 'refresh': True}) == 'analytics:write'


def test_public_block_analysis_can_compute_without_granting_refresh_or_ai_generation():
    owner = {'pk': 'athlete', 'profile_visibility': 'public', 'publication': {'domains': ['analytics']}}
    anonymous = evaluate_facts('', 'athlete', owner, None, [], {})
    for arguments in ({}, {'cacheOnly': False}, {'cacheOnly': True}):
        assert permits(anonymous, operation_permission('analytics.blocks_get', arguments))
    for arguments in ({'refresh': True}, {'cacheOnly': True, 'refresh': True}):
        assert not permits(anonymous, operation_permission('analytics.blocks_get', arguments))
    assert not permits(anonymous, operation_permission('analytics.block_evaluation', {}))
    assert permits(anonymous, operation_permission('analytics.block_evaluation', {'cacheOnly': True}))
    for hidden in ({**owner, 'profile_visibility': 'private'}, {**owner, 'publication': {'domains': ['program', 'sessions']}}):
        context = evaluate_facts('', 'athlete', hidden, None, [], {})
        assert not permits(context, operation_permission('analytics.blocks_get', {}))


def test_access_context_result_contract_accepts_actual_evaluator_fields():
    context = evaluate_facts('', 'athlete', None, None, [], {})
    load_operations('profile')['access_context'].validate_result(context)
    assert context['competition_scope'] == {'read': [], 'write': []}


def test_role_slot_prevents_superseded_grants_from_reactivating():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    owner = {'pk': 'owner', 'mapped_pk': 'athlete', 'roles': ['athlete']}
    actor = {'pk': 'old-coach', 'roles': ['coach']}
    old = {'relationship_id': 'old', 'grantee_person_pk': 'old-coach', 'grant_type': 'coach', 'tied_competition_ids': ['extended-meet']}
    new = {**old, 'relationship_id': 'new', 'grantee_person_pk': 'new-coach'}
    slot = {'entity': 'relationship_slot', 'grant_type': 'coach', 'relationship_id': 'new', 'state': 'active'}
    dates = {'extended-meet': '2099-01-01'}
    assert not permits(evaluate_facts('old-coach', 'athlete', owner, actor, [old, new, slot], dates, now), 'sessions:read')
    assert permits(evaluate_facts('new-coach', 'athlete', owner, {'pk': 'new-coach'}, [old, new, slot], dates, now), 'sessions:read')
    assert not permits(evaluate_facts('old-coach', 'athlete', owner, actor, [old, new], dates, now), 'sessions:read')
    peer = {'grantee_person_pk': 'old-coach', 'grant_type': 'peer', 'permissions': ['sessions:read']}
    assert permits(evaluate_facts('old-coach', 'athlete', owner, actor, [old, new, slot, peer], dates, now), 'sessions:read')
