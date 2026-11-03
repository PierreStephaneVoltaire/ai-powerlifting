from datetime import datetime, timezone

from services.access import evaluate_facts, permits, operation_permission, permission_map
from services.contract import load_operations


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


def test_access_context_result_contract_accepts_actual_evaluator_fields():
    from services.dispatch import dispatch
    context = evaluate_facts('', 'athlete', None, None, [], {})
    result = dispatch(load_operations('profile')['access_context'], {'_access': context})
    assert result['competition_scope'] == {'read': [], 'write': []}


def test_aggregate_program_changes_require_each_affected_domain():
    import pytest
    from services.authorization import check_context
    from services.dispatch import OperationError
    claims = {'iss': 'powerlifting-gateway'}
    limited = {'permissions': ['program:write', 'program:read']}
    for path in ('sessions[0].exercises', 'current_maxes.squat', 'meta.manual_maxes', 'competitions'):
        with pytest.raises(OperationError, match='permission required'):
            check_context('health_new_version', {'patches': [{'path': path, 'value': []}]}, claims, limited)
    with pytest.raises(OperationError, match='performance:write'):
        check_context('program_update_meta_field', {'updates': {'manual_maxes': {}}}, claims, limited)
    assert check_context('health_new_version', {'patches': [{'path': 'phases', 'value': []}]}, claims, limited) is limited
    tied = {'permissions': ['program:write', 'competition:write'], 'competition_scope': {'write': ['meet']}}
    with pytest.raises(OperationError, match='individual operations'):
        check_context('health_new_version', {'patches': [{'path': 'competitions', 'value': []}]}, claims, tied)
    template = {'permissions': ['templates:read', 'program:read', 'performance:read', 'glossary:read']}
    assert check_context('template_apply', {}, claims, template) is template
    with pytest.raises(OperationError, match='permission required'):
        check_context('template_apply_confirm', {}, claims, template)


def test_native_saved_result_checks_original_source_access():
    import pytest
    from services.authorization import check_context
    from services.dispatch import OperationError
    context = {'permissions': ['analytics:read', 'competition:read'], 'competition_scope': {'read': ['meet-a']}}
    arguments = {'cache_only': True, '_required_access': {'permissions': ['competition:read'], 'competition_ids': None}}
    with pytest.raises(OperationError, match='outside the current grant'):
        check_context('program_evaluation', arguments, {'iss': 'if-native'}, context)
    arguments['_required_access']['competition_ids'] = ['meet-a']
    assert check_context('program_evaluation', arguments, {'iss': 'if-native'}, context) is context


def test_cross_domain_metadata_and_note_permissions_are_checked():
    import pytest
    from services.authorization import check_context
    from services.dispatch import OperationError
    context = {'permissions': ['program:write', 'competition:read', 'settings:write', 'videos:write']}
    claims = {'iss': 'powerlifting-gateway'}
    with pytest.raises(OperationError, match='competition:write'):
        check_context('program_update_meta_field', {'field': 'attempt_pct', 'value': {}}, claims, context)
    with pytest.raises(OperationError, match='weight-log:write'):
        check_context('health_update_meta', {'updates': {'current_body_weight_kg': 80}}, claims, context)
    with pytest.raises(OperationError, match='lift-profiles:write'):
        check_context('video_upload_presign', {'lift': 'squat'}, claims, context)
    assert check_context('note_list_attachments', {'context_domain': 'competition'}, claims, context) is context
    with pytest.raises(OperationError):
        check_context('note_share', {'context_domain': 'competition'}, claims, context)
    assert operation_permission('note_share', {'context_domain': 'identity'}) is None
    assert operation_permission('health_list_competitions', {}) == 'competition:read'
    for arguments in ({'op': 'update'}, {'op': 'complete'}, {'master_id': 'meet', 'patch': {}}, {'master_id': 'meet', 'results': {}}):
        with pytest.raises(OperationError):
            check_context('health_list_competitions', arguments, claims, context)


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


def test_competition_ties_limit_writes_and_peer_reads_remain_independent():
    import pytest
    from services.authorization import check_context
    from services.dispatch import OperationError
    from services.publication import operation_result
    owner = {'pk': 'owner', 'mapped_pk': 'athlete', 'roles': ['athlete']}
    actor = {'pk': 'handler', 'roles': ['handler']}
    grant = {'grantee_person_pk': 'handler', 'grant_type': 'handler', 'tied_competition_ids': ['COMP#meet-a']}
    dates = {'COMP#meet-a': '2099-01-01'}
    context = evaluate_facts('handler', 'athlete', owner, actor, [grant], dates)
    claims = {'iss': 'powerlifting-gateway', 'athlete': 'athlete'}
    assert check_context('health_update_user_competition', {'master_id': 'meet-a'}, claims, context) is context
    for operation, arguments in [('health_update_user_competition', {'master_id': 'meet-b'}), ('health_complete_competition', {'date': '2099-01-01'}), ('health_list_competitions', {'op': 'update', 'master_id': 'meet-b'})]:
        with pytest.raises(OperationError, match='outside the current grant'):
            check_context(operation, arguments, claims, context)
    entries = [{'master_id': 'meet-a'}, {'master_id': 'meet-b'}]
    assert operation_result('health_list_competitions', entries, context) == entries[:1]
    assert operation_result('health_list_competitions', {'competitions': entries}, context) == {'competitions': entries[:1]}
    peer = {'grantee_person_pk': 'handler', 'grant_type': 'peer', 'permissions': ['competition:read']}
    context = evaluate_facts('handler', 'athlete', owner, actor, [grant, peer], dates)
    assert operation_result('health_list_competitions', entries, context) == entries
    assert operation_result('health_list_competitions', {'competitions': entries}, context) == {'competitions': entries}
    with pytest.raises(OperationError):
        check_context('health_update_user_competition', {'master_id': 'meet-b'}, claims, context)
