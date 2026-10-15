from types import SimpleNamespace

from services import handler_context as view
from services.access import evaluate_facts


def test_handler_context_filters_competition_ties_and_training_domains(monkeypatch):
    from services.lib import program_tool_helpers
    owner = {'pk': 'owner-person', 'mapped_pk': 'athlete'}
    actor = {'pk': 'handler-person'}
    entries = [{'pk': 'athlete', 'sk': 'COMP#tied', 'date': '2099-01-01', 'post_meet_report': {'attempts': [{'lift': 'squat', 'attempt_number': 1, 'kg': 150, 'result': 'made'}]}}, {'pk': 'athlete', 'sk': 'COMP#other', 'date': '2099-02-01'}]
    grant = {'grantee_person_pk': 'handler-person', 'grant_type': 'handler', 'tied_competition_ids': ['tied']}
    program = {'meta': {'current_block_id': 'block-1', 'blocks': [{'id': 'block-1', 'name': 'Strength', 'status': 'active'}], 'block_notes': [{'notes': 'Athlete-owned'}]}, 'sessions': [{'date': '2099-01-01', 'block': 'current', 'phase': {'name': 'Peak'}, 'videos': ['private-media']}], 'competitions': [{'date': '2020-01-01', 'results': {'squat_kg': 180, 'bench_kg': 100, 'deadlift_kg': 220}}]}
    async def get_program():
        return program
    monkeypatch.setattr(program_tool_helpers, 'get_store', lambda _args: SimpleNamespace(get_program=get_program))
    monkeypatch.setattr(view, 'person_record', lambda key: actor if key == actor['pk'] else owner)
    monkeypatch.setattr(view, 'visible_profile', lambda *_args, **_kwargs: {'display_name': 'Athlete', 'nickname': 'athlete'})
    monkeypatch.setattr(view, 'catalog', lambda: {})
    monkeypatch.setattr(view, 'database', lambda: SimpleNamespace(Table=lambda name: name))
    monkeypatch.setattr(view, 'pages', lambda table, *_args, **_kwargs: [grant] if table == 'if-powerlifting-requests' else entries)
    permissions = ['profile:read', 'program:read', 'competition:read', 'performance:read']
    def access():
        result = evaluate_facts(actor['pk'], 'athlete', owner, actor, [grant], {'tied': entries[0]['date']})
        return {**result, 'permissions': permissions}
    args = {'pk': 'athlete', '_person_pk': actor['pk'], '_access': access()}
    result = view.handler(args, None)
    assert [entry['sk'] for entry in result['competitions']] == ['COMP#tied']
    assert 'pk' not in result['competitions'][0]
    assert result['competitions'][0]['post_meet_report']['attempts'][0]['kg'] == 150
    assert result['estimated_maxes'] == {'squat': 180, 'bench': 100, 'deadlift': 220, 'method': 'comp_results'}
    assert result['phase'] == {'name': 'Peak'} and result['notes'] == [{'notes': 'Athlete-owned'}]
    result = view.handler({**args, '_access': {'is_self': False, 'permissions': ['competition:read']}}, None)
    assert result['estimated_maxes'] == {} and result['block'] is None and result['notes'] == []
    entries[0]['date'] = '2000-01-01'
    assert view.handler({**args, '_access': access()}, None)['competitions'] == []
    grant['revoked_at'] = 'now'
    entries[0]['date'] = '2099-01-01'
    assert view.handler({**args, '_access': access()}, None)['competitions'] == []
