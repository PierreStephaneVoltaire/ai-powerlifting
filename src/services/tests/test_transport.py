import importlib
import json

from fastapi.testclient import TestClient
from services.contract import load_operations


def test_http_mcp_calculation_parity_and_context(monkeypatch):
    monkeypatch.setenv('PL_DOMAIN', 'profile')
    module = importlib.reload(importlib.import_module('services.app'))
    monkeypatch.setattr(module, 'OPERATIONS', load_operations('calculations'))
    context = json.dumps({'person': '', 'athlete': '', 'operation': 'kg_to_lb', 'context': {'permissions': []}})
    with TestClient(module.app) as client:
        assert client.post('/operations/kg_to_lb', json={'kg': 100}).status_code == 403
        headers = {'X-PL-Access-Context': context}
        http = client.post('/operations/kg_to_lb', headers=headers, json={'kg': 100})
        assert http.status_code == 200, http.text
        response = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'kg_to_lb', 'arguments': {'kg': 100}}})
        assert response.json()['result']['structuredContent'] == http.json()
        schema = client.get('/openapi.json').json()['paths']['/operations/kg_to_lb']['post']['requestBody']['content']['application/json']['schema']
        listed = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}).json()['result']['tools']
        assert next(tool['inputSchema'] for tool in listed if tool['name'] == 'kg_to_lb') == schema
        assert client.post('/operations/kg_to_lb', headers=headers, json={'kg': 'bad'}).status_code == 422
        assert client.post('/operations/kg_to_lb', headers=headers, json={'kg': 1, '_person_pk': 'forged'}).status_code == 403
