import asyncio
from types import SimpleNamespace

from services.runtime import execution


def test_native_submission_excludes_transient_access_and_keeps_acting_person(monkeypatch):
    import httpx
    monkeypatch.setenv('IF_API_URL', 'http://native')
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
    assert sent[0]['headers']['X-Athlete-Pk'] == 'athlete-a'


def test_composite_report_contract_accepts_async_references_and_cache_misses():
    from services.runtime.contract import load_operations
    operations = load_operations('analytics-ai')
    for name in ('analytics.block_evaluation', 'analytics.correlation'):
        operations[name].validate_result({'generation_id': 'saved-reference', 'job_id': 'native-turn', 'status': 'starting'})
        operations[name].validate_result({'cached': False, 'cache_miss': True})
