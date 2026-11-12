import json
import hashlib
import os
import re
import time
from functools import lru_cache

import jwt

from services.handlers.user.identity_resolve.core import _get_table, _identity_key, _resolve_sync, _settings


AUDIENCE = 'powerlifting-services'
ISSUER = 'pl-security'


def workload(value):
    return value.removeprefix('spiffe://')


def mapping(name):
    value = json.loads(os.getenv(name, '{}'))
    if not isinstance(value, dict):
        raise ValueError('Invalid security configuration')
    return value


def service_for(caller):
    service = mapping('PL_SECURITY_WORKLOADS').get(workload(caller))
    if not isinstance(service, str) or not service.startswith('pl-'):
        raise ValueError('Unknown workload')
    return service


def allowed_edge(caller, destination):
    edges = mapping('PL_SECURITY_ALLOWED_CALLERS').get(workload(caller), [])
    if not isinstance(edges, list) or destination not in edges:
        raise ValueError('Workload edge denied')


@lru_cache(maxsize=1)
def jwks():
    url = os.environ['AUTHENTIK_JWKS_URL']
    if not url.startswith(('https://', 'http://')):
        raise ValueError('Invalid JWKS URL')
    return jwt.PyJWKClient(url, timeout=5)


def identity(token):
    issuer = os.environ['AUTHENTIK_ISSUER_URL']
    key = jwks().get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key.key, algorithms=['RS256'], issuer=issuer, audience=os.environ['AUTHENTIK_CLIENT_ID'], options={'require': ['iss', 'sub', 'aud', 'exp', 'iat']})
    if claims.get('azp') is not None and claims['azp'] != os.environ['AUTHENTIK_CLIENT_ID'] or isinstance(claims['aud'], list) and len(claims['aud']) > 1 and claims.get('azp') != os.environ['AUTHENTIK_CLIENT_ID']:
        raise ValueError('Invalid OIDC authorized party')
    if not isinstance(claims['sub'], str) or not claims['sub']:
        raise ValueError('Invalid identity subject')
    fallback = 'authentik_' + claims['sub']
    username = re.sub('[^a-z0-9_-]', '_', str(claims.get('preferred_username') or fallback).lower())[:32] or fallback
    discord = claims.get('discord_subjects', [])
    discord = [value for value in discord if isinstance(value, str) and re.fullmatch(r'\d{1,32}', value)] if isinstance(discord, list) else []
    return {'issuer': issuer, 'provider': 'authentik', 'sub': claims['sub'], 'username': username,
            'display_name': str(claims.get('name') or claims.get('preferred_username') or username),
            'avatar': claims.get('picture') if isinstance(claims.get('picture'), str) else None,
            'email': claims.get('email') if isinstance(claims.get('email'), str) else None,
            'groups': [str(value) for value in claims.get('groups', [])] if isinstance(claims.get('groups'), list) else [],
            'roles': [str(value) for value in claims.get('roles', [])] if isinstance(claims.get('roles'), list) else [],
            'discord_subjects': discord}


def resolve_identity(token):
    verified = identity(token)
    result = _resolve_sync({**verified, 'avatar_url': verified['avatar']})
    link_discord_subjects(result['settings']['pk'], verified['discord_subjects'])
    return {'identity': verified, **result}


def link_discord_subjects(person, subjects):
    subjects = sorted(set(subjects))
    if not subjects:
        return
    if not isinstance(person, str) or not person or len(subjects) > 99:
        raise ValueError('Invalid Discord aliases')
    table = _get_table()
    issuer = 'https://discord.com'
    writes = [{'ConditionCheck': {'TableName': table.name, 'Key': {'pk': person},
                                  'ConditionExpression': 'attribute_exists(pk)'}}]
    for subject in subjects:
        if not re.fullmatch(r'\d{1,32}', subject):
            raise ValueError('Invalid Discord subject')
        writes.append({'Put': {'TableName': table.name,
            'Item': {'pk': _identity_key(issuer, subject), 'mapped_pk': person, 'identity_issuer': issuer,
                     'identity_provider': 'discord', 'identity_sub': subject},
            'ConditionExpression': 'attribute_not_exists(pk) OR (mapped_pk = :person AND identity_issuer = :issuer AND identity_provider = :provider AND identity_sub = :subject)',
            'ExpressionAttributeValues': {':person': person, ':issuer': issuer, ':provider': 'discord', ':subject': subject}}})
    table.meta.client.transact_write_items(TransactItems=writes)


def existing_identity(token):
    verified = identity(token)
    table = _get_table()
    pointer = table.get_item(Key={'pk': _identity_key(verified['issuer'], verified['sub'])}, ConsistentRead=True).get('Item')
    if not pointer or not pointer.get('mapped_pk') or pointer.get('identity_issuer') != verified['issuer'] or pointer.get('identity_sub') != verified['sub']:
        raise ValueError('Identity must be resolved before minting')
    person = table.get_item(Key={'pk': pointer['mapped_pk']}, ConsistentRead=True).get('Item')
    if not person:
        raise ValueError('Linked Person is missing')
    return _settings(person)


def discord_identity(subject):
    if not isinstance(subject, str) or not re.fullmatch(r'\d{1,32}', subject):
        raise ValueError('Invalid Discord subject')
    issuer = 'https://discord.com'
    table = _get_table()
    pointer = table.get_item(Key={'pk': _identity_key(issuer, subject)}, ConsistentRead=True).get('Item')
    if not pointer or not pointer.get('mapped_pk') or pointer.get('identity_issuer') != issuer or pointer.get('identity_sub') != subject:
        raise ValueError('Discord subject is not linked')
    person = table.get_item(Key={'pk': pointer['mapped_pk']}, ConsistentRead=True).get('Item')
    if not person:
        raise ValueError('Linked Person is missing')
    return _settings(person)


def sign(person, athlete, operation, caller, destination, origin):
    now = int(time.time())
    claims = {'iss': ISSUER, 'aud': AUDIENCE, 'sub': person, 'athlete': athlete, 'operation': operation,
              'caller': workload(caller), 'destination': destination, 'origin': origin, 'iat': now, 'exp': now + 300}
    return jwt.encode(claims, os.environ['PL_SECURITY_PRIVATE_KEY'].replace('\\n', '\n'), algorithm='RS256')


def verify(token, operation='', caller='', destination=''):
    claims = jwt.decode(token, os.environ['PL_PRINCIPAL_PUBLIC_KEY'].replace('\\n', '\n'), algorithms=['RS256'], audience=AUDIENCE, issuer=ISSUER,
                        options={'require': ['sub', 'athlete', 'operation', 'caller', 'destination', 'origin', 'iat', 'exp']})
    if any(not isinstance(claims.get(key), str) for key in ('sub', 'athlete', 'operation', 'caller', 'destination', 'origin')):
        raise ValueError('Invalid principal scope')
    if claims['exp'] - claims['iat'] > 300 or claims['exp'] <= claims['iat']:
        raise ValueError('Invalid principal lifetime')
    if operation and claims['operation'] != operation or caller and claims['caller'] != workload(caller) or destination and claims['destination'] != destination:
        raise ValueError('Principal scope mismatch')
    return claims


def delegation_hash(allowed):
    return hashlib.sha256(json.dumps(sorted(set(allowed)), separators=(',', ':')).encode()).hexdigest()


def sign_job(claims, job_id, allowed):
    now = int(time.time())
    return jwt.encode({'iss': ISSUER, 'aud': 'powerlifting-coach-job', 'sub': claims['sub'], 'athlete': claims['athlete'],
                       'origin': claims['origin'], 'job_id': job_id, 'operation': claims['operation'], 'delegation_hash': delegation_hash(allowed),
                       'iat': now, 'exp': now + 3600}, os.environ['PL_SECURITY_PRIVATE_KEY'].replace('\\n', '\n'), algorithm='RS256')


def verify_job(token, job_id):
    claims = jwt.decode(token, os.environ['PL_PRINCIPAL_PUBLIC_KEY'].replace('\\n', '\n'), algorithms=['RS256'], audience='powerlifting-coach-job', issuer=ISSUER,
                        options={'require': ['sub', 'athlete', 'origin', 'job_id', 'operation', 'delegation_hash', 'iat', 'exp']})
    if not job_id or claims['job_id'] != job_id or claims['exp'] - claims['iat'] > 3600:
        raise ValueError('Invalid job capability')
    return claims
