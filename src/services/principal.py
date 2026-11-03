import os
import time

import jwt


ISSUERS = ('powerlifting-gateway', 'if-native')
AUDIENCE = 'powerlifting-services'


def principal_token(person: str, athlete: str, operation: str) -> str:
    secret = os.getenv('PL_PRINCIPAL_SECRET', '')
    if len(secret) < 32:
        raise RuntimeError('Principal signing is not configured')
    now = int(time.time())
    return jwt.encode({'sub': person, 'athlete': athlete, 'operation': operation, 'iss': 'if-native', 'aud': AUDIENCE, 'iat': now, 'exp': now + 300}, secret, algorithm='HS256')


def verify_principal(token: str, operation: str, person: str = '', athlete: str = '') -> dict:
    secret = os.getenv('PL_PRINCIPAL_SECRET', '')
    if len(secret) < 32:
        raise ValueError('Principal verification is not configured')
    claims = jwt.decode(token, secret, algorithms=['HS256'], audience=AUDIENCE, issuer=ISSUERS, options={'require': ['sub', 'iss', 'aud', 'iat', 'exp', 'athlete', 'operation']})
    if claims['operation'] != operation or not isinstance(claims['athlete'], str):
        raise ValueError('Principal operation mismatch')
    if (person and person != claims['sub']) or (athlete and athlete != claims['athlete']):
        raise ValueError('Principal scope mismatch')
    if claims['exp'] - claims['iat'] > 300:
        raise ValueError('Principal lifetime exceeds five minutes')
    return claims
