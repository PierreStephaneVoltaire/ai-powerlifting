import time

import jwt


AUDIENCE = "powerlifting-services"
ISSUERS = ("powerlifting-gateway", "if-native")
SIGNING_ISSUER = "if-native"
LIFETIME_SECONDS = 300


def sign(secret: str, person: str, athlete: str, operation: str) -> str:
    if len(secret) < 32:
        raise RuntimeError("Principal signing is not configured")
    now = int(time.time())
    claims = {"sub": person, "athlete": athlete, "operation": operation, "iss": SIGNING_ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + LIFETIME_SECONDS}
    return jwt.encode(claims, secret, algorithm="HS256")


def verify(secret: str, token: str, operation: str, person: str, athlete: str) -> dict:
    if len(secret) < 32:
        raise ValueError("Principal verification is not configured")
    claims = jwt.decode(token, secret, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUERS, options={"require": ["sub", "iss", "aud", "iat", "exp", "athlete", "operation"]})
    if claims["operation"] != operation or claims["sub"] != person or claims["athlete"] != athlete:
        raise ValueError("Principal scope mismatch")
    if claims["exp"] - claims["iat"] > LIFETIME_SECONDS:
        raise ValueError("Principal lifetime exceeds five minutes")
    return claims
