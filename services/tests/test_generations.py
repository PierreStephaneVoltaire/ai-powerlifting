import asyncio
from types import SimpleNamespace

from services import execution, generations


def test_report_fingerprint_tracks_source_and_window_not_read_flags():
    args = {'program': {'sessions': [{'kg': 100}]}, 'weeks': 4, 'window_start': '2026-08-03'}
    original = generations.fingerprint('block_correlation_analysis', args)
    assert generations.fingerprint('block_correlation_analysis', {**args, 'refresh': True, 'cache_only': True, '_if_job_id': 'turn'}) == original
    assert generations.fingerprint('block_correlation_analysis', {**args, 'weeks': 8}) != original
    assert generations.fingerprint('block_correlation_analysis', {**args, 'program': {'sessions': [{'kg': 105}]}}) != original
    assert generations.fingerprint('block_program_evaluation', args) != original


def test_cached_status_and_cache_only_never_submit_inference(monkeypatch):
    result = {'summary': 'validated report', 'findings': []}
    class Store:
        def __init__(self, athlete):
            assert athlete == 'athlete-a'
        def get(self, generation_id):
            return {'generation_id': generation_id, 'source_fingerprint': generation_id, 'status': 'succeeded', 'attempt': 1}
        def result(self, record):
            return result
        def reserve(self, *args):
            raise AssertionError('Read attempted to reserve a generation')
    monkeypatch.setattr(generations, 'GenerationStore', Store)
    monkeypatch.setattr(execution, 'GenerationStore', Store)
    async def check():
        status = await generations.status('reference', 'athlete-a', 'person-a', {'is_self': True})
        assert status['result'] == result and status['cached']
        cached = await execution.submit(SimpleNamespace(name='block_correlation_analysis'), {'program': {}, 'cache_only': True}, 'athlete-a', '')
        assert cached == result
    asyncio.run(check())


def test_native_submission_excludes_transient_access_and_keeps_acting_person(monkeypatch):
    import httpx
    import jwt
    monkeypatch.setenv('IF_API_URL', 'http://native')
    monkeypatch.setenv('INTERNAL_API_TOKEN', 'test-only')
    monkeypatch.setenv('PL_PRINCIPAL_SECRET', 'principal-test-secret-never-used-outside-tests')
    sent = []
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            sent.append(kwargs)
            return httpx.Response(202, json={'job_id': 'native', 'status': 'running'})
    monkeypatch.setattr(execution.httpx, 'AsyncClient', Client)
    asyncio.run(execution.submit(SimpleNamespace(name='template_parse', domain='templates'), {'pk': 'athlete-a', '_access': {'person_pk': 'coach'}, '_person_pk': 'coach'}, 'athlete-a', 'coach'))
    assert sent[0]['json']['payload']['arguments'] == {'pk': 'athlete-a'}
    assert sent[0]['headers']['X-Person-Pk'] == 'coach'
    claims = jwt.decode(sent[0]['headers']['X-PL-Principal'], options={'verify_signature': False})
    assert claims['sub'] == 'coach' and claims['athlete'] == 'athlete-a'


def test_report_submission_uses_access_for_source_before_persisting_payload(monkeypatch):
    import httpx
    monkeypatch.setenv('IF_API_URL', 'http://native')
    monkeypatch.setenv('INTERNAL_API_TOKEN', 'test-only')
    monkeypatch.setenv('PL_PRINCIPAL_SECRET', 'principal-test-secret-never-used-outside-tests')
    access = {'permissions': ['competition:read'], 'competition_scope': {'read': ['meet-a']}}
    seen = []
    async def source(arguments, athlete, operation):
        seen.append(arguments)
        return {'program': {'competitions': ['meet-a']}}
    class Store:
        def __init__(self, athlete):
            pass
        def reserve(self, *args):
            return {'generation_id': args[0], 'attempt': 1, 'status': 'starting'}, True
        def update(self, *args, **kwargs):
            pass
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return httpx.Response(202, json={'job_id': 'native', 'status': 'running'})
    monkeypatch.setattr(execution, 'report_source', source)
    monkeypatch.setattr(execution, 'GenerationStore', Store)
    monkeypatch.setattr(execution.httpx, 'AsyncClient', Client)
    asyncio.run(execution.submit(SimpleNamespace(name='program_evaluation', domain='analytics'), {'_access': access, '_person_pk': 'coach', 'program': {}}, 'athlete-a', 'coach'))
    assert seen == [{'_access': access, '_person_pk': 'coach', 'program': {}}]


def test_duplicate_generation_reuses_result_or_active_reference(monkeypatch):
    class Store:
        def __init__(self, athlete):
            pass
        def reserve(self, generation_id, *args):
            return {'generation_id': generation_id, 'job_id': 'native-turn', 'status': 'running'}, False
    monkeypatch.setattr(execution, 'GenerationStore', Store)
    async def check():
        operation = SimpleNamespace(name='block_correlation_analysis')
        first, second = await asyncio.gather(*(execution.submit(operation, {'program': {}, 'weeks': 4}, 'athlete-a', 'person-a') for _ in range(2)))
        assert first == second and first['job_id'] == 'native-turn'
    asyncio.run(check())


def test_composite_report_contract_accepts_async_references_and_cache_misses():
    from services.contract import load_operations
    operations = load_operations('analytics')
    for name in ('analytics.block_evaluation', 'analytics.correlation'):
        operations[name].validate_result({'generation_id': 'saved-reference', 'job_id': 'native-turn', 'status': 'starting'})
        operations[name].validate_result({'cached': False, 'cache_miss': True})


def test_generation_poll_uses_current_person_instead_of_original_owner(monkeypatch):
    import httpx
    import jwt
    monkeypatch.setenv('IF_API_URL', 'http://native')
    monkeypatch.setenv('INTERNAL_API_TOKEN', 'test-only')
    monkeypatch.setenv('PL_PRINCIPAL_SECRET', 'principal-test-secret-never-used-outside-tests')
    class Store:
        def __init__(self, athlete):
            pass
        def get(self, key):
            return {'generation_id': key, 'source_fingerprint': key, 'owner': 'revoked-person', 'status': 'running', 'job_id': 'job-a'}
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, headers):
            assert headers['X-Person-Pk'] == 'current-person'
            claims = jwt.decode(headers['X-PL-Principal'], options={'verify_signature': False})
            assert claims['sub'] == 'current-person' and claims['athlete'] == 'athlete-a'
            return httpx.Response(200, json={'status': 'running'}, request=httpx.Request('GET', url))
    monkeypatch.setattr(generations, 'GenerationStore', Store)
    monkeypatch.setattr(generations.httpx, 'AsyncClient', Client)
    assert asyncio.run(generations.status('reference', 'athlete-a', 'current-person', {'is_self': True}))['status'] == 'running'


def test_cached_generation_reference_rechecks_source_domains_and_competition_ties(monkeypatch):
    import pytest
    from services.dispatch import OperationError
    class Store:
        def __init__(self, athlete):
            pass
        def get(self, key):
            return {'generation_id': key, 'source_fingerprint': key, 'status': 'succeeded', 'access_requirements': {'permissions': ['program:read', 'competition:read'], 'competition_ids': ['meet-a', 'meet-b']}}
        def result(self, record):
            return {'summary': 'Both meets'}
    monkeypatch.setattr(generations, 'GenerationStore', Store)
    access = {'permissions': ['program:read', 'competition:read'], 'competition_scope': {'read': ['meet-a']}}
    with pytest.raises(OperationError, match='outside the current grant'):
        asyncio.run(generations.status('saved', 'athlete', 'handler', access))
    with pytest.raises(OperationError, match='Access .* changed'):
        asyncio.run(generations.status('saved', 'athlete', 'handler', {**access, 'permissions': ['competition:read']}))
    access['competition_scope']['read'].append('meet-b')
    assert asyncio.run(generations.status('saved', 'athlete', 'handler', access))['result'] == {'summary': 'Both meets'}
