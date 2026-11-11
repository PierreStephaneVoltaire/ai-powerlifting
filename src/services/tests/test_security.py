import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from envoy.service.auth.v3 import external_auth_pb2
from fastapi.testclient import TestClient

from services.security import credentials, ext_authz
from services.security.app import app


GATEWAY = 'cluster.local/ns/powerlifting/sa/powerlifting-app-backend'
DOMAIN = 'cluster.local/ns/powerlifting/sa/pl-calculations'
SECURITY = 'cluster.local/ns/powerlifting/sa/pl-security'


@pytest.fixture
def configured(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setenv('PL_SECURITY_PRIVATE_KEY', private)
    monkeypatch.setenv('PL_PRINCIPAL_PUBLIC_KEY', public)
    monkeypatch.setenv('PL_SECURITY_WORKLOADS', json.dumps({GATEWAY: 'pl-backend', DOMAIN: 'pl-calculations', SECURITY: 'pl-security'}))
    monkeypatch.setenv('PL_SECURITY_ALLOWED_CALLERS', json.dumps({GATEWAY: ['pl-calculations', 'pl-security']}))
    monkeypatch.setattr(ext_authz, 'current_context', lambda person, athlete: {'permissions': [], 'person_pk': person})


def check(token, body=b'{"kg":1}', source=GATEWAY, destination=DOMAIN, extra=None):
    headers = {'x-pl-principal': token, **(extra or {})}
    request = external_auth_pb2.CheckRequest()
    request.attributes.source.principal = 'spiffe://' + source
    request.attributes.destination.principal = 'spiffe://' + destination
    request.attributes.request.http.method = 'POST'
    request.attributes.request.http.path = '/operations/kg_to_lb'
    request.attributes.request.http.raw_body = body
    request.attributes.request.http.headers.update(headers)
    return ext_authz.Authorization('pl-security' if destination == SECURITY else 'pl-calculations').Check(request, None)


def test_principal_scope_and_forged_headers(configured):
    token = credentials.sign('', '', 'kg_to_lb', GATEWAY, 'pl-calculations', 'pl-backend')
    assert check(token).status.code == 0
    assert check(token, source=DOMAIN).status.code != 0
    assert check(token, extra={'x-person-pk': 'forged'}).status.code != 0
    assert check(token, destination=SECURITY).status.code != 0
    assert check(token, body=b'bad json').status.code != 0
    assert check(token, extra={'x-envoy-auth-partial-body': 'true'}).denied_response.status.code == 413
    response = check(token, extra={'x-pl-access-context': '{"person":"forged"}'})
    context = json.loads(next(item.header.value for item in response.ok_response.headers if item.header.key == 'x-pl-access-context'))
    assert context['person'] == '' and context['operation'] == 'kg_to_lb'


def test_gateway_workload_check_does_not_buffer_uploads(configured, monkeypatch):
    proxy = 'cluster.local/ns/powerlifting/sa/oauth2-proxy'
    monkeypatch.setenv('PL_SECURITY_WORKLOADS', json.dumps({proxy: 'pl-oauth2-proxy'}))
    monkeypatch.setenv('PL_SECURITY_ALLOWED_CALLERS', json.dumps({proxy: ['pl-backend']}))
    request = external_auth_pb2.CheckRequest()
    request.attributes.source.principal = 'spiffe://' + proxy
    request.attributes.request.http.method = 'POST'
    request.attributes.request.http.path = '/api/videos/upload'
    request.attributes.request.http.headers['content-length'] = str(100 * 1024 * 1024)
    assert ext_authz.Authorization('pl-backend').Check(request, None).status.code == 0
    request.attributes.source.principal = 'spiffe://' + GATEWAY
    assert ext_authz.Authorization('pl-backend').Check(request, None).status.code != 0


def test_mint_rejects_unknown_target_and_impersonation(configured):
    client = TestClient(app)
    headers = {'x-pl-mesh-caller': GATEWAY}
    body = {'operation': 'kg_to_lb', 'destination': 'pl-calculations', 'athlete': ''}
    response = client.post('/v1/principals', json=body, headers=headers)
    assert response.status_code == 200
    claims = credentials.verify(response.json()['principal'], 'kg_to_lb', GATEWAY, 'pl-calculations')
    assert claims['sub'] == ''
    assert client.post('/v1/principals', json={**body, 'destination': 'pl-security'}, headers=headers).status_code == 403
    assert client.post('/v1/principals', json={**body, 'discord_subject': '123'}, headers=headers).status_code == 403
    assert client.post('/v1/principals', json=body).status_code == 403


def test_verified_person_not_athlete_and_job_scope(configured, monkeypatch):
    coach = 'cluster.local/ns/powerlifting/sa/pl-coach'
    monkeypatch.setenv('PL_SECURITY_WORKLOADS', json.dumps({GATEWAY: 'pl-backend', DOMAIN: 'pl-calculations', SECURITY: 'pl-security', coach: 'pl-coach'}))
    monkeypatch.setenv('PL_SECURITY_ALLOWED_CALLERS', json.dumps({GATEWAY: ['pl-coach'], coach: ['pl-calculations']}))
    monkeypatch.setenv('PL_SECURITY_DELEGATION', json.dumps({'conversation_turn': ['kg_to_lb']}))
    monkeypatch.setattr(credentials, 'existing_identity', lambda token: {'pk': 'person', 'mapped_pk': 'athlete'})
    client = TestClient(app)
    response = client.post('/v1/principals', headers={'x-pl-mesh-caller': GATEWAY}, json={'identity_token': 'verified', 'operation': 'conversation_turn', 'destination': 'pl-coach', 'athlete': 'athlete'})
    assert response.status_code == 200
    incoming = response.json()['principal']
    assert credentials.verify(incoming)['sub'] == 'person'
    job = client.post('/v1/job-capabilities', headers={'x-pl-mesh-caller': coach}, json={'principal': incoming, 'job_id': 'job-1'}).json()['capability']
    request = {'capability': job, 'job_id': 'job-1', 'operation': 'kg_to_lb', 'destination': 'pl-calculations', 'athlete': 'athlete'}
    issued = client.post('/v1/principals', headers={'x-pl-mesh-caller': coach}, json=request)
    assert issued.status_code == 200
    assert credentials.verify(issued.json()['principal'])['sub'] == 'person'
    assert client.post('/v1/principals', headers={'x-pl-mesh-caller': coach}, json={**request, 'job_id': 'job-2'}).status_code == 403
    assert client.post('/v1/principals', headers={'x-pl-mesh-caller': coach}, json={**request, 'athlete': 'other'}).status_code == 403
    monkeypatch.setenv('PL_SECURITY_DELEGATION', json.dumps({'conversation_turn': ['kg_to_lb', 'calculate_dots']}))
    assert client.post('/v1/principals', headers={'x-pl-mesh-caller': coach}, json=request).status_code == 403


def test_oidc_signature_issuer_and_audience_are_verified(configured, monkeypatch):
    import time
    from types import SimpleNamespace
    import jwt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv('AUTHENTIK_ISSUER_URL', 'https://auth.example/application/o/app/')
    monkeypatch.setenv('AUTHENTIK_CLIENT_ID', 'client')
    monkeypatch.setattr(credentials, 'jwks', lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    now = int(time.time())
    claims = {'iss': 'https://auth.example/application/o/app/', 'aud': 'client', 'sub': 'verified', 'iat': now, 'exp': now + 60, 'discord_subjects': ['42', 'not-a-subject']}
    assert credentials.identity(jwt.encode(claims, key, algorithm='RS256'))['discord_subjects'] == ['42']
    for change in ({'aud': 'other'}, {'iss': 'https://attacker.example/'}, {'exp': now - 1}):
        with pytest.raises(jwt.InvalidTokenError):
            credentials.identity(jwt.encode({**claims, **change}, key, algorithm='RS256'))
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidTokenError):
        credentials.identity(jwt.encode(claims, other, algorithm='RS256'))
