"""Lightweight smoke tests for the new grant_* core modules.

Run with:  python3 lambda/tests/test_grant_core.py
"""
import sys
import os
import asyncio
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LAMBDA_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LAMBDA_DIR)

# Stub out boto3 / AWS modules so this can run offline.
try:
    import boto3  # noqa: F401
except ImportError:
    import types
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.resource = lambda *a, **kw: None
    boto3_stub.client = lambda *a, **kw: None
    sys.modules["boto3"] = boto3_stub
    from boto3.dynamodb.conditions import Key  # type: ignore  # noqa
    boto3_stub.dynamodb = types.ModuleType("boto3.dynamodb")
    boto3_stub.dynamodb.conditions = types.ModuleType("boto3.dynamodb.conditions")
    sys.modules["boto3.dynamodb.conditions"].Key = lambda *a, **kw: None

from pod_user.handlers._shared import requests_table as shared
from pod_user.handlers.grant_create import core as grant_create
from pod_user.handlers.grant_revoke import core as grant_revoke
from pod_user.handlers.grant_list import core as grant_list
from pod_user.handlers.grant_check import core as grant_check


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_build_pk_and_sk():
    pk = shared.build_pk("athlete-1")
    _assert(pk == "Grant#athlete-1", f"unexpected pk: {pk}")
    sk = shared.build_sk("grantee-1", "2024-01-01T00:00:00+00:00", "coach")
    _assert(sk.startswith("Grantee#grantee-1#2024-01-01T00:00:00"), f"unexpected sk: {sk}")
    _assert(sk.endswith("#coach"), f"sk should end with type, got: {sk}")


def test_is_active():
    now = datetime.now(timezone.utc)
    g = {"revoked_at": None, "expires_at": (now + timedelta(days=1)).isoformat()}
    _assert(shared.is_active(g), "future grant should be active")
    g2 = {"revoked_at": now.isoformat(), "expires_at": (now + timedelta(days=1)).isoformat()}
    _assert(not shared.is_active(g2), "revoked grant should be inactive")
    g3 = {"revoked_at": None, "expires_at": (now - timedelta(days=1)).isoformat()}
    _assert(not shared.is_active(g3), "expired grant should be inactive")


def test_grant_create_validation():
    err, _ = grant_create._validate_args({
        "athlete_mapped_pk": "athlete-1",
        "grantee_mapped_pk": "athlete-1",
        "grant_type": "coach",
    })
    _assert(err == "cannot_grant_to_self", f"expected cannot_grant_to_self, got {err}")

    err, _ = grant_create._validate_args({
        "athlete_mapped_pk": "athlete-1",
        "grantee_mapped_pk": "grantee-1",
        "grant_type": "boss",
    })
    _assert(err == "invalid_grant_type", f"expected invalid_grant_type, got {err}")

    err, _ = grant_create._validate_args({
        "athlete_mapped_pk": "athlete-1",
        "grantee_mapped_pk": "grantee-1",
        "grant_type": "coach",
        "scope": "admin",
    })
    _assert(err == "invalid_scope", f"expected invalid_scope, got {err}")

    err, _ = grant_create._validate_args({
        "athlete_mapped_pk": "!@#",
        "grantee_mapped_pk": "grantee-1",
        "grant_type": "coach",
    })
    _assert(err == "invalid_athlete_mapped_pk", f"got {err}")

    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    err, grant = grant_create._validate_args({
        "athlete_mapped_pk": "athlete-1",
        "grantee_mapped_pk": "grantee-1",
        "grant_type": "coach",
        "scope": "read",
        "tied_competition_ids": ["ipf-2026"],
        "tied_competition_dates": {"ipf-2026": future},
    })
    _assert(err is None, f"unexpected validation error: {err}")
    _assert(grant["pk"] == "Grant#athlete-1", f"bad pk: {grant['pk']}")
    _assert(grant["grant_type"] == "coach", f"bad grant_type: {grant['grant_type']}")
    _assert(grant["scope"] == "read", f"bad scope: {grant['scope']}")
    exp = datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
    expected_exp = datetime.fromisoformat(future) + timedelta(days=grant_create.EXPIRY_TAIL_DAYS)
    _assert(abs((exp - expected_exp).total_seconds()) < 2, f"expires_at drift: {exp} vs {expected_exp}")

    err, grant = grant_create._validate_args({
        "athlete_mapped_pk": "athlete-1",
        "grantee_mapped_pk": "grantee-1",
        "grant_type": "handler",
    })
    _assert(err is None, f"unexpected validation error: {err}")
    _assert(grant["grant_type"] == "handler", f"bad grant_type: {grant['grant_type']}")
    _assert(grant["scope"] == "read", f"bad scope: {grant['scope']}")


def test_grant_check_self():
    result = asyncio.run(grant_check.grant_check({
        "athlete_mapped_pk": "athlete-1",
        "actor_mapped_pk": "athlete-1",
    }))
    _assert(result["allowed"] is True, f"self check should be allowed: {result}")
    _assert(result["reason"] == "self", f"reason should be self, got {result['reason']}")


if __name__ == "__main__":
    tests = [
        test_build_pk_and_sk,
        test_is_active,
        test_grant_create_validation,
        test_grant_check_self,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed")
