import asyncio

import pytest
from jsonschema import ValidationError

from services.contract import load_operations


def test_profile_inventory_has_complete_contract_shapes():
    operations = load_operations("profile")

    assert {
        "master_copy_seed_user",
        "profile_get",
        "profile_search",
        "settings_create",
        "settings_get",
        "settings_update_athlete_basics",
        "onboarding_status",
    } <= operations.keys()
    assert all(operation.result_schema for operation in operations.values())
    assert operations["profile_search"].result_schema["required"] == ["profiles"]
    assert operations["settings_create"].result_schema["required"] == ["settings", "created"]
    assert operations["settings_get"].result_schema["required"][:4] == [
        "pk",
        "username",
        "discord_id",
        "discord_username",
    ]


def test_profile_contracts_reject_incomplete_mutations():
    operations = load_operations("profile")

    for name in (
        "settings_create",
        "settings_update_nickname",
        "settings_update_avatar",
        "settings_update_athlete_basics",
        "settings_update_onboarding_profile",
        "settings_update_role",
        "settings_tag_add",
    ):
        with pytest.raises(ValidationError):
            operations[name].validate_input({})

    with pytest.raises(ValidationError):
        operations["settings_update_avatar"].validate_input(
            {"username": "athlete", "file_b64": "aGVsbG8=", "mimetype": "text/plain"}
        )


def test_profile_result_schema_preserves_extended_profile_shape():
    profile = {
        "nickname": "lifter",
        "display_name": "Lifter",
        "avatar_url": "profiles/lifter/avatar.png",
        "bio": "Training",
        "profile_visibility": "public",
        "public_training_summary_enabled": True,
        "is_self": False,
        "tags": ["powerlifting"],
        "federation": "IPF",
        "weight_class_kg": 83,
        "practicing_for": None,
        "summary": {
            "squat_kg": 180,
            "bench_kg": 120,
            "deadlift_kg": 220,
            "total_kg": 520,
            "bodyweight_kg": 82.5,
            "dots": 350,
        },
        "lift_videos": [],
    }
    load_operations("profile")["profile_get"].validate_result(profile)
    load_operations("profile")["profile_search"].validate_result({"profiles": [profile]})


def test_profile_summary_uses_loaded_sessions_and_canonical_dots():
    module = __import__(
        "services.handlers.user.profile_get.core",
        fromlist=["_build_profile"],
    )
    settings = {
        "nickname": "lifter",
        "display_name": "Lifter",
        "avatar_url": None,
        "bio": "",
        "profile_visibility": "public",
        "public_training_summary_enabled": True,
        "tags": [],
    }
    sessions = [
        {
            "date": "2026-09-13",
            "completed": True,
            "body_weight_kg": 82.5,
            "exercises": [
                {"name": "Squat", "kg": 180, "sets": 1},
                {"name": "Bench Press", "kg": 120, "sets": 1},
                {"name": "Deadlift", "kg": 220, "sets": 1},
            ],
        }
    ]
    result = module._build_profile(
        settings,
        "viewer",
        {"meta": {"sex": "male"}},
        sessions,
    )

    assert result["summary"]["total_kg"] == 520
    assert result["summary"]["bodyweight_kg"] == 82.5
    assert result["summary"]["dots"] == 352.24


def test_onboarding_status_routes_through_shared_state(monkeypatch):
    module = __import__(
        "services.handlers.user.onboarding_status.core",
        fromlist=["onboarding_status"],
    )

    async def fake_settings_get(_args):
        return {
            "roles": ["athlete"],
            "active_role": "athlete",
            "profile_complete": True,
            "sex": "female",
            "bodyweight_kg": 63,
            "training_maxes": {
                "squat_kg": 100,
                "bench_kg": 60,
                "deadlift_kg": 120,
            },
        }

    monkeypatch.setattr(module, "settings_get", fake_settings_get)
    result = asyncio.run(module.onboarding_status({"username": "lifter"}))

    assert result["is_onboarded"] is True
    assert result["next_step"] == "done"
    assert result["state"]["active_role"] == "athlete"


def test_settings_get_default_is_contract_complete(monkeypatch):
    module = __import__(
        "services.handlers.user.settings_get.core",
        fromlist=["settings_get"],
    )
    monkeypatch.setattr(module, "_get_table", lambda: object())
    result = asyncio.run(module.settings_get({}))

    load_operations("profile")["settings_get"].validate_result(result)
    assert result["roles"] == []
    assert result["active_role"] == "athlete"


def test_unachieved_targets_and_unknown_sex_are_not_profile_results():
    from importlib import import_module
    core = import_module('services.handlers.user.profile_get.core')
    assert core._resolved_lift({'meta': {'target_squat_kg': 300}}, 'squat') is None
    settings = {'nickname': 'athlete', 'profile_visibility': 'public'}
    result = core._build_profile(settings, None, {'current_maxes': {'squat': 100, 'bench': 100, 'deadlift': 100}, 'meta': {'current_body_weight_kg': 80}}, [])
    assert result['summary']['dots'] is None


def test_settings_update_role_aliases_reserved_roles_attribute(monkeypatch):
    module = __import__(
        "services.handlers.user.settings_update_role.core",
        fromlist=["settings_update_role"],
    )

    class Table:
        name = "if-user"

        def __init__(self):
            self.item = {"pk": "lifter", "username": "lifter", "roles": []}
            self.update = None

        def get_item(self, **_kwargs):
            return {"Item": dict(self.item)}

        def update_item(self, **kwargs):
            self.update = kwargs
            self.item.update({"roles": kwargs["ExpressionAttributeValues"][":roles"], "active_role": kwargs["ExpressionAttributeValues"][":active"]})

    table = Table()
    monkeypatch.setattr(module, "_get_table", lambda: table)
    result = asyncio.run(module.settings_update_role({"username": "lifter", "roles": ["athlete"], "active_role": "athlete"}))

    assert result["roles"] == ["athlete"]
    assert table.update["ExpressionAttributeNames"] == {"#roles": "roles"}
    assert "#roles" in table.update["UpdateExpression"]
