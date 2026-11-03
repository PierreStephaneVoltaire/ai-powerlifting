from datetime import datetime, timezone

import pytest

from services import profile_views as views
from services.access import evaluate_facts
from services.dispatch import OperationError


def test_public_baseline_current_grants_and_approved_search_pagination(monkeypatch):
    owners = [{'pk': f'person-{i:02}', 'mapped_pk': f'athlete-{i:02}', 'nickname': f'lifter-{i:02}', 'display_name': f'Lifter {i:02}', 'roles': ['athlete'], 'profile_visibility': 'public', 'federations': ['IPF'], 'bio': 'private original', 'discord_id': 'sensitive', 'tags': [{'tag': 'approved', 'approved': False}, {'tag': 'pending', 'approved': True}]} for i in range(23)]
    private = {**owners[0], 'pk': 'private-person', 'mapped_pk': 'private-athlete', 'nickname': 'private', 'display_name': 'Private', 'profile_visibility': 'private'}
    owners.append(private)
    grants = [{'grantee_person_pk': 'coach', 'grant_type': 'coach', 'tied_competition_ids': ['meet']}]
    by_athlete = {owner['mapped_pk']: owner for owner in owners}
    actor = {'pk': 'coach', 'roles': ['coach']}
    vocabulary = {'approved': {'status': 'approved'}, 'pending': {'status': 'pending'}}
    monkeypatch.setattr(views, 'people', lambda: owners)
    monkeypatch.setattr(views, 'catalog', lambda: vocabulary)
    monkeypatch.setattr(views, '_current_program', lambda athlete: ('program#v001', {'meta': {'federation': 'CPU', 'weight_class_kg': 83}, 'phases': []}))
    monkeypatch.setattr(views, 'current_context', lambda person, athlete: evaluate_facts(person, athlete, by_athlete[athlete], actor if person == 'coach' else None, grants if athlete == 'private-athlete' else [], {'meet': '2099-01-01'}, datetime(2026, 9, 14, tzinfo=timezone.utc)))
    first = views.search({'tags': ['approved'], 'federations': ['IPF']})
    assert len(first['profiles']) == 20 and first['next_cursor']
    baseline = first['profiles'][0]
    assert baseline['bio'] == 'private original' and baseline['tags'] == ['approved']
    assert baseline['federation'] == 'CPU'
    assert baseline['lift_videos'] == [] and baseline['summary']['bodyweight_kg'] is None
    assert not {'discord_id', 'pk', 'grants', 'notifications'} & baseline.keys()
    second = views.search({'tags': ['approved'], 'federations': ['IPF'], 'cursor': first['next_cursor']})
    assert len(second['profiles']) == 3 and second['next_cursor'] is None
    assert not {p['nickname'] for p in first['profiles']} & {p['nickname'] for p in second['profiles']}
    with pytest.raises(ValueError, match='cursor'):
        views.search({'query': 'different', 'cursor': first['next_cursor']})
    assert views.search({'tags': ['pending']})['profiles'] == []
    assert len(views.search({'query': 'private', '_person_pk': 'coach'})['profiles']) == 1
    assert views.visible_profile(private, 'coach', vocabulary)['bio'] == 'private original'
    grants[0]['revoked_at'] = 'now'
    assert views.search({'query': 'private', '_person_pk': 'coach'})['profiles'] == []
    with pytest.raises(OperationError, match='not found'):
        views.get_by_handle({'nickname': 'private', '_person_pk': 'coach'})
    vocabulary['approved']['status'] = 'rejected'
    assert views.search({'tags': ['approved']})['profiles'] == []


def test_public_profile_reports_main_federation_and_dots_without_bodyweight(monkeypatch):
    owner = {'pk': 'person', 'mapped_pk': 'athlete', 'nickname': 'lifter', 'display_name': 'Lifter', 'roles': ['athlete'], 'profile_visibility': 'public', 'federations': [], 'bio': 'Meet prep for nationals'}
    program = {'meta': {'federation': 'CPU', 'weight_class_kg': 83, 'sex': 'male', 'current_body_weight_kg': 82}, 'phases': [], 'current_maxes': {'squat': 210, 'bench': 122.5, 'deadlift': 225}}
    access = {'permissions': ['profile:read', 'performance:read', 'competition:read', 'analytics:read'], 'is_self': False, 'granted_permissions': []}
    monkeypatch.setattr(views, '_current_program', lambda athlete: ('program#v001', program))
    monkeypatch.setattr(views, 'current_context', lambda person, athlete: access)
    from services.lib.session_store import SessionStore
    monkeypatch.setattr(SessionStore, 'list_sessions_sync', lambda self, *_args, **_kwargs: [])
    profile = views.visible_profile(owner, '', {}, details=True)
    assert profile['bio'] == 'Meet prep for nationals'
    assert profile['federation'] == 'CPU' and profile['weight_class_kg'] == 83
    assert profile['summary']['total_kg'] == 557.5
    assert profile['summary']['dots'] and profile['summary']['dots'] > 370
    assert profile['summary']['bodyweight_kg'] is None
