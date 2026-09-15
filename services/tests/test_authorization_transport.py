import importlib
import time

from fastapi.testclient import TestClient
import jwt

from services.access import evaluate_facts
from services.contract import load_operations


def test_http_and_mcp_recheck_grants_and_reject_forged_identity(monkeypatch):
    secret = 'principal-test-secret-never-used-outside-tests'
    monkeypatch.setenv('PL_DOMAIN', 'profile')
    monkeypatch.setenv('PL_PRINCIPAL_SECRET', secret)
    monkeypatch.setenv('INTERNAL_API_TOKEN', 'transport-test')
    module = importlib.reload(importlib.import_module('services.app'))
    authorization = importlib.import_module('services.authorization')
    monkeypatch.setattr(module, 'OPERATIONS', load_operations())
    owner = {'pk': 'owner', 'mapped_pk': 'athlete', 'roles': ['athlete'], 'sex': 'female', 'bodyweight_kg': 75, 'training_maxes': {'squat_kg': 150, 'bench_kg': 100, 'deadlift_kg': 200}}
    actors = {'owner': owner, 'coach': {'pk': 'coach', 'roles': ['coach']}}
    grants = [{'grantee_mapped_pk': 'coach', 'grant_type': 'coach', 'tied_competition_ids': ['meet']}]
    monkeypatch.setattr(authorization, 'current_context', lambda person, athlete: evaluate_facts(person, athlete, owner, actors.get(person), grants, {'meet': '2099-01-01'}))
    calls = []
    monkeypatch.setattr(module, 'dispatch', lambda operation, arguments: calls.append(arguments) or {'ok': True})

    def headers(operation, person='coach', **extra):
        now = int(time.time())
        token = jwt.encode({'sub': person, 'athlete': 'athlete', 'iss': 'powerlifting-gateway', 'aud': 'powerlifting-services', 'operation': operation, 'iat': now, 'exp': now + 300}, secret, algorithm='HS256')
        return {'X-Internal-Token': 'transport-test', 'X-PL-Principal': token, **extra}

    with TestClient(module.app) as client:
        assert client.post('/operations/session_list', headers={'X-Internal-Token': 'transport-test', 'X-Person-Pk': 'owner', 'X-Athlete-Pk': 'athlete'}, json={}).status_code == 401
        assert client.post('/operations/session_list', headers=headers('session_list', **{'X-Person-Pk': 'owner'}), json={}).status_code == 401
        assert client.post('/operations/session_list', headers=headers('session_get'), json={}).status_code == 401
        assert client.post('/operations/session_list', headers=headers('session_list'), json={}).status_code == 200
        grants[0]['revoked_at'] = '2026-09-14'
        assert client.post('/operations/session_list', headers=headers('session_list'), json={}).status_code == 403
        mcp = client.post('/mcp', headers=headers('session_list'), json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'session_list', 'arguments': {}}}).json()
        assert mcp['result']['isError'] is True
        assert client.post('/operations/settings_update_profile', headers=headers('settings_update_profile', 'owner'), json={'username': 'victim', 'display_name': 'forged'}).status_code == 403
        assert client.post('/operations/settings_get', headers=headers('settings_get', 'owner'), json={'identity_provider': 'authentik', 'identity_sub': 'victim'}).status_code == 403
        assert client.post('/operations/profile_get', headers=headers('profile_get', 'owner'), json={'nickname': 'victim', 'viewer_username': 'victim'}).status_code == 403
        assert client.post('/operations/identity_resolve', headers=headers('identity_resolve', 'owner'), json={'issuer': 'forged', 'provider': 'authentik', 'sub': 'fake', 'discord_subjects': ['1234']}).status_code == 403
        assert len(calls) == 1
        basics = {'sex': 'male', 'country': 'CA', 'bodyweight_kg': 80, 'training_maxes': {'squat_kg': 150, 'bench_kg': 100, 'deadlift_kg': 200}}
        for invalid in ({'maxes_date': 42}, {'maxes_date': '2026-02-31'}, {'training_maxes_estimated': {'squat': 'yes'}}):
            response = client.post('/operations/settings_update_athlete_basics', headers=headers('settings_update_athlete_basics', 'owner'), json={'username': 'owner', 'input': {**basics, **invalid}})
            assert response.status_code == 422, response.text
        from services.dispatch import unwrap
        conflict = {'code': 'conflict', 'message': 'Program changed', 'current_revision': 8, 'current_record': {'meta': {'revision': 8}}}
        monkeypatch.setattr(module, 'dispatch', lambda *args: unwrap({'statusCode': 409, 'body': conflict}))
        arguments = {'action': 'complete', 'block_id': 'current', 'expected_revision': 7, 'idempotency_key': 'transition'}
        response = client.post('/operations/block_transition', headers=headers('block_transition', 'owner'), json=arguments)
        assert response.status_code == 409 and response.json()['detail'] == conflict
        response = client.post('/mcp', headers=headers('block_transition', 'owner'), json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'block_transition', 'arguments': arguments}})
        import json
        assert json.loads(response.json()['result']['content'][0]['text']) == {'error': conflict, 'status': 409}
        grants[0].pop('revoked_at')
        grants[0]['permissions'] = ['program:read', 'program:write']
        conflict['current_record'] = {'meta': {'program_name': 'Visible', 'manual_maxes': {'squat': 200}, 'current_body_weight_kg': 90}}
        response = client.post('/operations/program_update_meta_field', headers=headers('program_update_meta_field'), json={'field': 'program_name', 'value': 'Edit', 'expected_revision': 7, 'idempotency_key': 'edit'})
        assert response.status_code == 409
        assert response.json()['detail']['current_record']['meta'] == {'program_name': 'Visible'}
