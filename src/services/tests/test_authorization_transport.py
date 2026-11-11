import json

from envoy.service.auth.v3 import external_auth_pb2

from services.access import evaluate_facts
from services.security import credentials, ext_authz
from services.tests.test_security import DOMAIN, GATEWAY, configured


def test_http_and_mcp_recheck_grants(configured, monkeypatch):
    owner = {'pk': 'owner', 'mapped_pk': 'athlete', 'roles': ['athlete']}
    coach = {'pk': 'coach', 'roles': ['coach']}
    grants = [{'grantee_mapped_pk': 'coach', 'grant_type': 'coach', 'tied_competition_ids': ['meet']}]
    monkeypatch.setattr(ext_authz, 'current_context', lambda person, athlete: evaluate_facts(person, athlete, owner, coach, grants, {'meet': '2099-01-01'}))
    token = credentials.sign('coach', 'athlete', 'session_list', GATEWAY, 'pl-sessions', 'pl-backend')
    monkeypatch.setenv('PL_SECURITY_ALLOWED_CALLERS', json.dumps({GATEWAY: ['pl-sessions']}))
    request = external_auth_pb2.CheckRequest()
    request.attributes.source.principal = 'spiffe://' + GATEWAY
    http = request.attributes.request.http
    http.method = 'POST'
    http.headers['x-pl-principal'] = token
    http.path = '/operations/session_list'
    http.raw_body = b'{}'
    service = ext_authz.Authorization('pl-sessions')
    assert service.Check(request, None).status.code == 0
    http.path = '/mcp'
    http.raw_body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'session_list', 'arguments': {}}}).encode()
    assert service.Check(request, None).status.code == 0
    grants[0]['revoked_at'] = '2026-09-14'
    assert service.Check(request, None).status.code != 0
    http.path = '/operations/session_list'
    http.raw_body = b'{}'
    assert service.Check(request, None).status.code != 0
