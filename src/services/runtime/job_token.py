import os
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from . import llm_log

ISSUER = 'pl-assistant'
AUDIENCE = 'pl-domain-mcp'
LEEWAY_SECONDS = 30
PUBLIC_KEY_ENV = 'PL_JOB_TOKEN_PUBLIC_KEY'
REQUIRED_CLAIMS = ('exp', 'iss', 'aud', 'jti', 'person_pk', 'athlete_pk')
BEARER_PREFIX = 'bearer '


class JobTokenRejected(Exception):
    pass


@dataclass(frozen=True)
class MeshIdentity:
    person: str
    athlete: str
    source: str


def bearer_token(authorization: str) -> str | None:
    value = authorization.strip()
    if value[:len(BEARER_PREFIX)].lower() != BEARER_PREFIX:
        return None
    return value[len(BEARER_PREFIX):].strip()


def load_public_key(pem: str):
    if not pem.strip():
        return None
    try:
        key = serialization.load_pem_public_key(pem.encode())
    except ValueError:
        return None
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != 'secp256r1':
        return None
    return key


def audit(decision: str, operation: str, claims: dict[str, Any] | None = None, reason: str = '') -> None:
    claims = claims or {}
    llm_log.emit('job_token', jti=claims.get('jti'), person_pk=claims.get('person_pk'), operation=operation, decision=decision, reason=reason or None)


def verify(token: str, public_key) -> dict[str, Any]:
    if public_key is None:
        raise JobTokenRejected('token authentication disabled')
    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=['ES256'],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=LEEWAY_SECONDS,
            options={'require': list(REQUIRED_CLAIMS)},
        )
    except jwt.PyJWTError as exc:
        raise JobTokenRejected(type(exc).__name__) from exc
    if not all(isinstance(claims[name], str) and claims[name] for name in ('jti', 'person_pk', 'athlete_pk')):
        raise JobTokenRejected('required claim empty')
    if not isinstance(claims.get('scope'), list):
        raise JobTokenRejected('scope claim missing')
    return claims


def resolve_mcp_identity(authorization: str, mesh: MeshIdentity, method: str, params: dict[str, Any], public_key=None) -> tuple[MeshIdentity, bool]:
    token = bearer_token(authorization)
    if token is None:
        return mesh, False
    operation = str(params.get('name', '')) if method == 'tools/call' else ''
    if mesh.person or mesh.athlete:
        audit('deny', operation, reason='identity headers combined with bearer token')
        raise JobTokenRejected('identity headers combined with bearer token')
    try:
        claims = verify(token, public_key if public_key is not None else configured_public_key())
    except JobTokenRejected as exc:
        audit('deny', operation, reason=str(exc))
        raise
    if method == 'tools/call' and operation not in claims['scope']:
        audit('deny', operation, claims, 'operation outside token scope')
        raise JobTokenRejected('operation outside token scope')
    audit('accept', operation, claims)
    return MeshIdentity(person=claims['person_pk'], athlete=claims['athlete_pk'], source=''), True


def configured_public_key():
    return load_public_key(os.environ.get(PUBLIC_KEY_ENV, ''))
