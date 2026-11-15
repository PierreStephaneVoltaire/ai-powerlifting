from services.runtime import publication


def test_program_view_projects_nested_domains():
    program = {'sessions': [{'id': 'session1', 'body_weight_kg': 83, 'videos': ['video']}], 'competitions': ['meet'], 'lift_profiles': ['profile'], 'meta': {'program_name': 'Block', 'current_body_weight_kg': 83, 'manual_maxes': {}, 'blocks': [{'id': 'block1', 'start_maxes_kg': {'squat': 150}}]}}
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


def test_public_viewers_see_only_current_block_sessions():
    program = {'meta': {}, 'sessions': [{'date': '2026-10-01', 'block': 'current'}, {'date': '2025-01-01', 'block': 'ottawa-prep'}, {'date': '2026-10-02'}]}
    public = {'is_self': False, 'permissions': ['program:read', 'sessions:read'], 'granted_permissions': []}
    coach = {**public, 'granted_permissions': ['sessions:read']}
    owner = {**public, 'is_self': True}
    assert [s['date'] for s in publication.program_view(program, public)['sessions']] == ['2026-10-01', '2026-10-02']
    assert len(publication.program_view(program, coach)['sessions']) == 3
    assert len(publication.operation_result('program_get', program, owner)['sessions']) == 3
    assert [s['date'] for s in publication.operation_result('session_list', program['sessions'], public)] == ['2026-10-01', '2026-10-02']
