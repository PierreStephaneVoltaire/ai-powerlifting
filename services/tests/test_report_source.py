import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services import generations


def test_report_source_does_not_load_unpermitted_federations(monkeypatch):
    federation_store = importlib.import_module('lambda.pod_federation.handlers._federation_store')
    constructor = Mock(side_effect=AssertionError('Unpermitted federation read'))
    monkeypatch.setattr(federation_store, 'FederationStore', constructor)
    source = asyncio.run(generations.report_source({'program': {}, '_access': {'permissions': ['program:read']}}, 'athlete', 'program_evaluation'))
    assert source['federation_library'] == []
    constructor.assert_not_called()


def test_report_source_loads_authorized_federations_from_existing_store(monkeypatch):
    federation_store = importlib.import_module('lambda.pod_federation.handlers._federation_store')
    library = {'federations': [{'name': 'Fixture federation'}], 'qualification_standards': []}
    constructor = Mock(return_value=SimpleNamespace(get_library=AsyncMock(return_value=library)))
    monkeypatch.setattr(federation_store, 'FederationStore', constructor)
    source = asyncio.run(generations.report_source({'program': {}, '_access': {'permissions': ['program:read', 'federation:read']}}, 'athlete', 'program_evaluation'))
    assert source['federation_library'] == library
    assert constructor.call_args.kwargs['pk'] == 'athlete'


@pytest.mark.parametrize('name', ['program_evaluation', 'block_program_evaluation', 'correlation_analysis'])
def test_report_handlers_preserve_empty_filtered_sources(monkeypatch, name):
    core = importlib.import_module(f'lambda.pod_analysis.handlers.{name}.core')
    store = SimpleNamespace(pk='athlete', invalidate_cache=Mock(), get_program=AsyncMock(side_effect=AssertionError('Private Program reload')))
    federation_store = Mock(side_effect=AssertionError('Private federation reload'))
    if hasattr(core, '_get_store'):
        monkeypatch.setattr(core, '_get_store', lambda: store)
    if hasattr(core, '_get_federation_store'):
        monkeypatch.setattr(core, '_get_federation_store', federation_store)
    table = SimpleNamespace(put_item=Mock(), get_item=Mock(side_effect=AssertionError('Legacy cache read')))
    monkeypatch.setattr('boto3.resource', lambda *args, **kwargs: SimpleNamespace(Table=lambda name: table))
    ai_name = 'correlation_ai' if name == 'correlation_analysis' else 'program_evaluation_ai'
    function_name = 'generate_correlation_report' if name == 'correlation_analysis' else 'generate_program_evaluation_report'
    ai = importlib.import_module(f'lambda.pod_analysis.handlers.{name}.{ai_name}')
    generate = AsyncMock(return_value={'summary': 'Filtered report'})
    monkeypatch.setattr(ai, function_name, generate)
    result = getattr(core, name)({'program': {}, '_report_source': {'program': {}, 'federation_library': []}, 'refresh': True})
    store.get_program.assert_not_called()
    federation_store.assert_not_called()
    if name == 'program_evaluation':
        assert result['insufficient_data'] is True
    elif name == 'block_program_evaluation':
        assert generate.call_args.kwargs['federation_library'] == []
    else:
        assert generate.call_args.kwargs['program'] == {}
