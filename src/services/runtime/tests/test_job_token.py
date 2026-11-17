import base64
import hashlib
import hmac
import importlib
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from services.runtime import job_token
from services.runtime.access import evaluate_facts

BACKEND = 'spiffe://cluster.local/ns/powerlifting/sa/powerlifting-app-backend'


def key_pair():
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


SIGNING, PUBLIC_PEM = key_pair()
OTHER, _ = key_pair()


def hs256_token(secret):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=')
    signing_input = part({'alg': 'HS256', 'typ': 'JWT'}) + b'.' + part(claims())
    signature = base64.urlsafe_b64encode(hmac.new(secret, signing_input, hashlib.sha256).digest()).rstrip(b'=')
    return (signing_input + b'.' + signature).decode()


def claims(**overrides):
    base = {'person_pk': 'person-1', 'athlete_pk': 'athlete-1', 'conversation_id': 'c', 'workflow_id': 'w', 'scope': ['session_list'], 'aud': 'pl-domain-mcp', 'iss': 'pl-assistant', 'jti': 'jti-1', 'exp': int(time.time()) + 300}
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def token(key=SIGNING, algorithm='ES256', **overrides):
    return jwt.encode(claims(**overrides), key, algorithm=algorithm)


def resolve(value, method='tools/call', name='session_list', mesh=job_token.MeshIdentity('', '', ''), key=None):
    return job_token.resolve_mcp_identity(f'Bearer {value}', mesh, method, {'name': name}, key or job_token.load_public_key(PUBLIC_PEM))


def test_happy_path_identity_from_token_and_audit(monkeypatch):
    events = []
    monkeypatch.setattr(job_token.llm_log, 'emit', lambda event, **fields: events.append((event, fields)))
    identity, bearer = resolve(token())
    assert bearer and (identity.person, identity.athlete, identity.source) == ('person-1', 'athlete-1', '')
    assert events == [('job_token', {'jti': 'jti-1', 'person_pk': 'person-1', 'operation': 'session_list', 'decision': 'accept', 'reason': None})]


def test_rejected_tokens_audit_deny(monkeypatch):
    events = []
    monkeypatch.setattr(job_token.llm_log, 'emit', lambda event, **fields: events.append(fields))
    forged = token(key=OTHER)
    hs256 = hs256_token(PUBLIC_PEM.encode())
    unsigned = jwt.encode(claims(), None, algorithm='none')
    cases = {
        'forged': forged,
        'expired': token(exp=int(time.time()) - 120),
        'no_exp': token(exp=None),
        'wrong_aud': token(aud='other'),
        'wrong_iss': token(iss='someone'),
        'no_jti': token(jti=None),
        'empty_person': token(person_pk=''),
        'alg_none': unsigned,
        'hs256_confusion': hs256,
        'garbage': 'not-a-jwt',
    }
    for name, value in cases.items():
        with pytest.raises(job_token.JobTokenRejected):
            resolve(value)
    assert len(events) == len(cases) and all(event['decision'] == 'deny' for event in events)


def test_small_clock_skew_tolerated():
    identity, _ = resolve(token(exp=int(time.time()) - 10))
    assert identity.person == 'person-1'


def test_scope_miss_denied():
    with pytest.raises(job_token.JobTokenRejected):
        resolve(token(), name='session_delete')


def test_missing_scope_claim_denied():
    with pytest.raises(job_token.JobTokenRejected):
        resolve(token(scope=None))


def test_disabled_key_denies_every_bearer(monkeypatch):
    monkeypatch.delenv('PL_JOB_TOKEN_PUBLIC_KEY', raising=False)
    with pytest.raises(job_token.JobTokenRejected):
        job_token.resolve_mcp_identity(f'Bearer {token()}', job_token.MeshIdentity('', '', ''), 'tools/call', {'name': 'session_list'})


def test_bearer_cannot_combine_with_mesh_identity():
    with pytest.raises(job_token.JobTokenRejected):
        resolve(token(), mesh=job_token.MeshIdentity('victim', '', ''))
    with pytest.raises(job_token.JobTokenRejected):
        resolve(token(), mesh=job_token.MeshIdentity('', 'victim', ''))
    identity, _ = resolve(token(), mesh=job_token.MeshIdentity('', '', BACKEND))
    assert identity.source == ''


def test_no_bearer_leaves_mesh_identity_untouched():
    mesh = job_token.MeshIdentity('p', 'a', BACKEND)
    assert job_token.resolve_mcp_identity('', mesh, 'tools/call', {'name': 'x'}) == (mesh, False)


def services_app(monkeypatch):
    monkeypatch.setenv('PL_DOMAIN', 'sessions')
    monkeypatch.setenv('PL_JOB_TOKEN_PUBLIC_KEY', PUBLIC_PEM)
    module = importlib.reload(importlib.import_module('services.runtime.app'))
    monkeypatch.setattr(module, 'dispatch', lambda operation, arguments: {'ok': True})
    return module


def call_body(name='session_list'):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}}


def test_mcp_bearer_runs_existing_authorization_with_token_identity(monkeypatch):
    module = services_app(monkeypatch)
    seen = []
    owner = {'pk': 'athlete-1', 'profile_visibility': 'public', 'publication': {'domains': ['sessions']}}
    actor = {'pk': 'person-1', 'roles': []}

    def context(person, athlete):
        seen.append((person, athlete))
        return evaluate_facts(person, athlete, owner, actor, [], {})

    monkeypatch.setattr(module, 'current_context', context)
    with TestClient(module.app) as client:
        response = client.post('/mcp', headers={'Authorization': f'Bearer {token()}'}, json=call_body())
        assert response.json()['result']['isError'] is False
        assert seen == [('person-1', 'athlete-1')]
        assert client.post('/mcp', headers={'Authorization': f'Bearer {token(key=OTHER)}'}, json=call_body()).status_code == 401
        assert client.post('/mcp', headers={'Authorization': f'Bearer {token()}'}, json=call_body('session_delete')).status_code == 401
        assert client.post('/mcp', headers={'Authorization': f'Bearer {token()}', 'X-Person-Pk': 'victim'}, json=call_body()).status_code == 401
