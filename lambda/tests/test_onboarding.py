"""Smoke tests for the onboarding lambdas (role / profile / athlete basics).

Run with:  python3 lambda/tests/test_onboarding.py
"""
import sys
import os
import asyncio
from decimal import Decimal
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LAMBDA_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LAMBDA_DIR)

try:
    import boto3  # type: ignore
except ImportError:
    import types
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.resource = lambda *a, **kw: None
    boto3_stub.client = lambda *a, **kw: None
    sys.modules["boto3"] = boto3_stub
    from botocore.exceptions import ClientError  # type: ignore  # noqa

from pod_user.handlers.settings_update_athlete_basics import core as athlete_basics
from pod_user.handlers.settings_update_onboarding_profile import core as onboarding_profile
from pod_user.handlers.settings_update_role import core as role


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_athlete_basics_validation_min():
    out = athlete_basics._validate_athlete_basics({
        "sex": "male",
        "country": "us",
        "region": " ca ",
        "bodyweight_kg": 82.5,
        "training_maxes": {"squat_kg": 180, "bench_kg": 120, "deadlift_kg": 220},
    })
    _assert(out["sex"] == "male", "sex normalised")
    _assert(out["country"] == "US", "country uppercased")
    _assert(out["region"] == "ca", "region stripped")
    _assert(out["bodyweight_kg"] == 82.5, "bodyweight kept")
    _assert(out["training_maxes"]["squat_kg"] == 180, "squat kept")
    _assert(out["training_maxes"]["deadlift_kg"] == 220, "deadlift kept")


def test_athlete_basics_validation_rejects_zero_max():
    raised = False
    try:
        athlete_basics._validate_athlete_basics({
            "sex": "male",
            "country": "US",
            "bodyweight_kg": 80,
            "training_maxes": {"squat_kg": 0, "bench_kg": 100, "deadlift_kg": 200},
        })
    except ValueError:
        raised = True
    _assert(raised, "squat_kg of 0 must be rejected")


def test_athlete_basics_validation_rejects_missing_sex():
    raised = False
    try:
        athlete_basics._validate_athlete_basics({
            "country": "US",
            "bodyweight_kg": 80,
            "training_maxes": {"squat_kg": 100, "bench_kg": 100, "deadlift_kg": 200},
        })
    except ValueError:
        raised = True
    _assert(raised, "missing sex must be rejected")


def test_athlete_basics_validation_rejects_bad_sex():
    raised = False
    try:
        athlete_basics._validate_athlete_basics({
            "sex": "unknown",
            "country": "US",
            "bodyweight_kg": 80,
            "training_maxes": {"squat_kg": 100, "bench_kg": 100, "deadlift_kg": 200},
        })
    except ValueError:
        raised = True
    _assert(raised, "sex='unknown' must be rejected (no 'unknown' allowed for athletes)")


def test_athlete_basics_validation_rejects_low_bodyweight():
    raised = False
    try:
        athlete_basics._validate_athlete_basics({
            "sex": "male",
            "country": "US",
            "bodyweight_kg": 10,
            "training_maxes": {"squat_kg": 100, "bench_kg": 100, "deadlift_kg": 200},
        })
    except ValueError:
        raised = True
    _assert(raised, "10kg bodyweight must be rejected")


def test_athlete_basics_requires_athlete_role():
    fake_table = mock.MagicMock()
    fake_table.get_item.return_value = {"Item": {"pk": "alice", "roles": ["coach"]}}
    with mock.patch.object(athlete_basics, "_get_table", return_value=fake_table):
        async def run():
            try:
                await athlete_basics.settings_update_athlete_basics({
                    "username": "alice",
                    "input": {
                        "sex": "male",
                        "country": "US",
                        "bodyweight_kg": 80,
                        "training_maxes": {"squat_kg": 100, "bench_kg": 100, "deadlift_kg": 200},
                    },
                })
            except ValueError as e:
                return str(e)
            return None
        msg = asyncio.run(run())
    _assert(msg and "athlete" in msg, f"non-athlete should be blocked, got: {msg!r}")


def test_onboarding_profile_validation_min():
    out = onboarding_profile._validate({
        "display_name": "Squat McLifter",
        "bio": "ok",
        "profile_visibility": "public",
        "public_training_summary_enabled": True,
        "federations": ["ipf", "usapl"],
    })
    _assert(out["display_name"] == "Squat McLifter", "display name kept")
    _assert(out["federations"] == ["ipf", "usapl"], "federations kept")
    _assert(out["profile_visibility"] == "public", "visibility kept")


def test_onboarding_profile_rejects_empty_display_name():
    raised = False
    try:
        onboarding_profile._validate({"display_name": "   "})
    except ValueError:
        raised = True
    _assert(raised, "blank display_name must be rejected")


def test_onboarding_profile_truncates_long_display_name():
    out = onboarding_profile._validate({"display_name": "x" * 200})
    _assert(len(out["display_name"]) == 80, f"display_name must be truncated to 80, got {len(out['display_name'])}")


def test_onboarding_profile_caps_federations():
    out = onboarding_profile._validate({
        "display_name": "ok",
        "federations": [f"f{i}" for i in range(50)],
    })
    _assert(len(out["federations"]) <= 20, f"federations must be capped, got {len(out['federations'])}")


def test_onboarding_profile_allows_no_federations():
    out = onboarding_profile._validate({"display_name": "ok"})
    _assert(out["federations"] is None, "federations omitted = None (no overwrite)")


def test_role_requires_at_least_one():
    raised = False
    try:
        asyncio.run(role.settings_update_role({"username": "alice", "roles": []}))
    except ValueError:
        raised = True
    _assert(raised, "empty roles must be rejected")


def test_role_rejects_unknown_role():
    raised = False
    try:
        asyncio.run(role.settings_update_role({"username": "alice", "roles": ["owner"]}))
    except ValueError:
        raised = True
    _assert(raised, "unknown role must be rejected")


def test_role_rejects_active_role_not_in_list():
    raised = False
    try:
        asyncio.run(role.settings_update_role({
            "username": "alice",
            "roles": ["athlete", "coach"],
            "active_role": "handler",
        }))
    except ValueError:
        raised = True
    _assert(raised, "active_role outside roles list must be rejected")


def test_role_normalize():
    out = role._read_roles(["athlete", "coach", "owner", "athlete"])
    _assert(out == ["athlete", "coach"], f"unexpected roles: {out}")


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
