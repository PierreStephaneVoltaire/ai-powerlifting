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
        status = await generations.status('reference', 'athlete-a')
        assert status['result'] == result and status['cached']
        cached = await execution.submit(SimpleNamespace(name='block_correlation_analysis'), {'program': {}, 'cache_only': True}, 'athlete-a', 'person-a')
        assert cached == result
    asyncio.run(check())


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
