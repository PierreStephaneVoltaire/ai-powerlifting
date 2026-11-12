import importlib

from fastapi.testclient import TestClient

from services.access import evaluate_facts

BACKEND = 'spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend'
COACH = 'spiffe://cluster.local/ns/powerlifting/sa/pl-coach'


def services_app(monkeypatch, domain):
    monkeypatch.setenv('PL_DOMAIN', domain)
    module = importlib.reload(importlib.import_module('services.app'))
    monkeypatch.setattr(module, 'dispatch', lambda operation, arguments: {'ok': True})
    return module


def mcp_call(client, name, headers):
    response = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}})
    return response.json()['result']


def test_http_and_mcp_recheck_grants(monkeypatch):
    module = services_app(monkeypatch, 'sessions')
    owner = {'pk': 'owner', 'mapped_pk': 'athlete', 'roles': ['athlete']}
    coach = {'pk': 'coach', 'roles': ['coach']}
    grants = [{'grantee_mapped_pk': 'coach', 'grant_type': 'coach', 'tied_competition_ids': ['meet']}]
    monkeypatch.setattr(module, 'current_context', lambda person, athlete: evaluate_facts(person, athlete, owner, coach, grants, {'meet': '2099-01-01'}))
    headers = {'X-Person-Pk': 'coach', 'X-Athlete-Pk': 'athlete', 'X-PL-Source-Principal': BACKEND}
    with TestClient(module.app) as client:
        assert client.post('/operations/session_list', headers=headers, json={}).status_code == 200
        assert mcp_call(client, 'session_list', headers)['isError'] is False
        grants[0]['revoked_at'] = '2026-09-14'
        assert client.post('/operations/session_list', headers=headers, json={}).status_code == 403
        assert mcp_call(client, 'session_list', headers)['isError'] is True


def test_access_store_failure_denies_http_and_mcp(monkeypatch):
    module = services_app(monkeypatch, 'sessions')

    def unavailable(person, athlete):
        raise RuntimeError('store unavailable')

    monkeypatch.setattr(module, 'current_context', unavailable)
    headers = {'X-Person-Pk': 'person', 'X-Athlete-Pk': 'athlete', 'X-PL-Source-Principal': BACKEND}
    with TestClient(module.app, raise_server_exceptions=False) as client:
        assert client.post('/operations/session_list', headers=headers, json={}).status_code == 500
        mcp = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'session_list', 'arguments': {}}})
        assert mcp.status_code == 500


def test_internal_operations_are_backend_only(monkeypatch):
    module = services_app(monkeypatch, 'profile')
    monkeypatch.setattr(module, 'current_context', lambda person, athlete: {'permissions': []})
    arguments = {'issuer': 'https://auth.example/', 'provider': 'authentik', 'sub': 'subject'}
    with TestClient(module.app) as client:
        assert client.post('/operations/identity_resolve', headers={'X-PL-Source-Principal': BACKEND}, json=arguments).status_code == 200
        assert client.post('/operations/identity_resolve', headers={'X-PL-Source-Principal': COACH}, json=arguments).status_code == 403
        assert client.post('/operations/identity_resolve', json=arguments).status_code == 403


def test_access_context_authorizes_a_named_operation(monkeypatch):
    module = services_app(monkeypatch, 'profile')
    monkeypatch.setattr(module, 'dispatch', lambda operation, arguments: arguments['_access'])
    monkeypatch.setattr(module, 'current_context', lambda person, athlete: {'permissions': ['sessions:read']})
    headers = {'X-Person-Pk': 'person', 'X-Athlete-Pk': 'athlete', 'X-PL-Source-Principal': COACH}
    with TestClient(module.app) as client:
        assert client.post('/operations/access_context', headers=headers, json={}).json() == {'permissions': ['sessions:read']}
        assert client.post('/operations/access_context', headers=headers, json={'operation': 'session_list', 'arguments': {}}).status_code == 200
        assert client.post('/operations/access_context', headers=headers, json={'operation': 'session_patch', 'arguments': {}}).status_code == 403
        assert client.post('/operations/access_context', headers=headers, json={'operation': 'identity_resolve', 'arguments': {}}).status_code == 403
