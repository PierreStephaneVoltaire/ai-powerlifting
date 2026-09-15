import copy

import pytest

from services import publication
from services.dispatch import OperationError


def test_publication_owner_cas_and_nested_domain_projection(monkeypatch):
    owner = {'pk': 'athlete-person', 'roles': ['athlete']}
    class Table:
        def get_item(self, **kwargs):
            assert kwargs['Key'] == {'pk': owner['pk']}
            return {'Item': copy.deepcopy(owner)}
        def update_item(self, **kwargs):
            assert 'publication.revision = :expected' in kwargs['ConditionExpression']
            owner['publication'] = copy.deepcopy(kwargs['ExpressionAttributeValues'][':publication'])
    class Database:
        def Table(self, name):
            return Table()
    monkeypatch.setattr(publication, 'database', Database)
    args = {'_access': {'settings_pk': owner['pk']}, 'domains': ['program'], 'expected_revision': 0, 'idempotency_key': 'publish'}
    current = publication.handler(args, None)
    assert current['domains'] == ['program'] and current['revision'] == 1
    assert publication.handler(args, None) == current
    with pytest.raises(OperationError, match='changed'):
        publication.handler({**args, 'idempotency_key': 'stale'}, None)
    owner['roles'] = ['coach']
    with pytest.raises(OperationError, match='Athletes'):
        publication.handler({**args, 'expected_revision': 1, 'idempotency_key': 'coach'}, None)
    program = {'sessions': [{'id': 'session1', 'body_weight_kg': 83, 'videos': ['video']}], 'competitions': ['meet'], 'lift_profiles': ['profile'], 'meta': {'program_name': 'Block', 'last_comp': {'private': True}, 'current_body_weight_kg': 83, 'manual_maxes': {}, 'blocks': [{'id': 'block1', 'start_maxes_kg': {'squat': 150}}]}}
    access = {'permissions': ['program:read', 'sessions:read']}
    visible = publication.program_view(program, access)
    assert visible['sessions'] == [{'id': 'session1'}]
    assert visible['competitions'] == [] and visible['lift_profiles'] == []
    assert visible['meta'] == {'program_name': 'Block', 'blocks': [{'id': 'block1'}]}
    assert program['sessions'][0]['videos'] == ['video']


def test_operation_result_fails_closed_without_access():
    program = {'sessions': [{'id': 'session1'}], 'meta': {'program_name': 'Private'}}
    result = publication.operation_result('program_get', program, {})
    assert result['sessions'] == [] and result['meta'] == {}


def test_publication_get_projects_internal_metadata(monkeypatch):
    owner = {'pk': 'athlete-person', 'roles': ['athlete'], 'publication': {
        'domains': ['competition'], 'revision': 3, 'idempotency_key': 'private-key', 'updated_at': '2026-09-15T00:00:00Z',
    }}

    class Table:
        def get_item(self, **kwargs):
            return {'Item': owner}

    class Database:
        def Table(self, name):
            return Table()

    monkeypatch.setattr(publication, 'database', Database)
    assert publication.handler({'_access': {'settings_pk': 'athlete-person'}}, None) == {'domains': ['competition'], 'revision': 3}
