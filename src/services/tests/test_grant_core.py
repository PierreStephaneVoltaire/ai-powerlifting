"""Lightweight smoke tests for the new grant_* core modules.

Run with:  python3 -m pytest src/services/tests/test_grant_core.py
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

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

from services.handlers.user._shared import requests_table as shared
from services.handlers.user.grant_create import core as grant_create
from services.handlers.user.grant_revoke import core as grant_revoke
from services.handlers.user.grant_list import core as grant_list
from services.handlers.user.grant_check import core as grant_check


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
