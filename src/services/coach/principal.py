import os

import jwt


AUDIENCE = "powerlifting-services"
LIFETIME_SECONDS = 300


def verify(token: str, operation: str, person: str, athlete: str) -> dict:
    claims = jwt.decode(token, os.environ['PL_PRINCIPAL_PUBLIC_KEY'].replace('\\n', '\n'), algorithms=['RS256'], audience=AUDIENCE, issuer='pl-security', options={'require': ['sub', 'iss', 'aud', 'iat', 'exp', 'athlete', 'operation', 'destination']})
    if claims['operation'] != operation or claims['sub'] != person or claims['athlete'] != athlete or claims['destination'] != 'pl-coach' or claims['exp'] - claims['iat'] > LIFETIME_SECONDS:
        raise ValueError('Principal scope mismatch')
    return claims
