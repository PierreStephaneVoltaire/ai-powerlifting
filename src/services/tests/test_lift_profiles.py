import importlib
import json

import httpx
import pytest


from services.contract import load_operations
from services.dispatch import dispatch


BENCH_OPTIONS = {
    "grip_width": "wide", "bar_in_hand": "low_palm_thumb_wrapped", "touch_point": "lower_chest", "arch": "moderate",
    "elbows_descent": "45_degrees", "feet": "heels_down", "leg_drive": "timed", "descent_speed": "controlled",
    "at_chest": "sink", "bar_path": "j_curve", "sticking_point": "mid_range",
}


def _tool_response(arguments):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"tool_calls": [{"function": {"arguments": json.dumps(arguments)}}]}}]},
        request=httpx.Request("POST", "http://fake"),
    )


def test_lift_profile_contracts_describe_all_outputs():
    operations = load_operations("lift-profiles")
    assert list(operations) == [
        "fatigue_profile_estimate",
        "muscle_group_estimate",
        "lift_profile_estimate_stimulus",
        "lift_profile_suggest",
        "program_update_lift_profiles",
    ]
    assert all(operation.result_schema for operation in operations.values())
    for operation in operations.values():
        with pytest.raises(Exception):
            operation.validate_input({})


def test_option_definitions_match_the_requested_form():
    from services.lib.lift_profiles import definitions, fields

    assert [field["key"] for field in fields("bench")] == ["grip_width", "bar_in_hand", "touch_point", "arch", "elbows_descent", "feet", "leg_drive", "descent_speed", "at_chest", "bar_path", "sticking_point"]
    assert [field["key"] for field in fields("squat")] == ["bar_position", "hand_width", "stance", "toe_angle", "descent", "knee_gear", "sticking_point"]
    assert [field["key"] for field in fields("deadlift")] == ["stance", "grip", "start", "hip_height", "sticking_point"]
    assert [option["value"] for option in definitions()["common"][0]["options"]] == ["low", "moderate", "high"]


def test_clean_validates_options_locks_sumo_hips_and_keeps_old_text_in_notes():
    from services.lib.lift_profiles import clean

    cleaned = clean({
        "lift": "deadlift", "options": {"stance": "sumo", "hip_height": "high", "grip": "made_up"},
        "style_notes": "Sumo, wedge hard", "sticking_points": "Off the floor", "primary_muscle": "Quads",
        "failure_nodes": ["hips shoot up"], "volume_tolerance": "extreme", "e1rm_multiplier": 1.02, "notes": "Grip fails past 250",
    })
    assert cleaned["options"] == {"stance": "sumo", "hip_height": "low"}
    assert cleaned["volume_tolerance"] == "moderate"
    assert cleaned["notes"] == "Grip fails past 250"
    assert not {"style_notes", "sticking_points", "primary_muscle", "failure_nodes"} & set(cleaned)
    assert cleaned["e1rm_multiplier"] == 1.02
    assert clean({**cleaned, "lift": "deadlift"})["notes"] == cleaned["notes"]


def test_describe_and_missing_use_option_labels():
    from services.lib.lift_profiles import clean, describe, missing, technique_text

    profile = clean({"lift": "squat", "options": {"bar_position": "low", "stance": "shoulder_width"}, "volume_tolerance": "high"})
    assert describe(profile)["technique"] == {"Bar position": "Low", "Stance": "Shoulder width"}
    assert technique_text(profile) == "Bar position: Low; Stance: Shoulder width"
    assert missing(profile) == ["Hand width", "Toe angle", "Descent", "Knee gear", "Sticking point"]


def test_suggest_keeps_known_options_ignores_nulls_and_invalid_values(monkeypatch):
    module = importlib.import_module("services.lib.lift_profile_ai")

    async def fake_completion(payload):
        assert payload["tools"][0]["function"]["name"] == "select_lift_profile_options"
        assert "grip_width" in payload["tools"][0]["function"]["parameters"]["properties"]
        return _tool_response({"grip_width": "wide", "arch": None, "touch_point": "not_an_option", "leg_drive": "timed", "volume_tolerance": "low"})

    monkeypatch.setattr(module, "completion", fake_completion)
    operation = load_operations("lift-profiles")["lift_profile_suggest"]
    result = dispatch(operation, {"lift": "bench", "description": "wide grip, I time my leg drive", "profile": {"lift": "bench", "options": {"arch": "max"}}})
    operation.validate_result(result)
    assert result["options"] == {"grip_width": "wide", "arch": "max", "leg_drive": "timed"}
    assert result["changed"] == ["grip_width", "leg_drive"]
    assert result["volume_tolerance"] == "low"


def test_estimate_requires_every_option_then_returns_the_coefficient(monkeypatch):
    module = importlib.import_module("services.lib.lift_profile_ai")
    operation = load_operations("lift-profiles")["lift_profile_estimate_stimulus"]
    with pytest.raises(Exception, match="Choose every option"):
        dispatch(operation, {"profile": {"lift": "bench", "options": {"grip_width": "wide"}}})

    async def fake_completion(payload):
        assert "Grip width: Wide" in payload["messages"][1]["content"] or '"Grip width": "Wide"' in payload["messages"][1]["content"]
        return _tool_response({"stimulus_coefficient": 1.23, "confidence": "medium", "reasoning": "Wide grip and moderate arch shorten ROM."})

    monkeypatch.setattr(module, "completion", fake_completion)
    result = dispatch(operation, {"profile": {"lift": "bench", "options": BENCH_OPTIONS, "volume_tolerance": "moderate"}})
    operation.validate_result(result)
    assert result["stimulus_coefficient"] == 1.25 and result["stimulus_coefficient_confidence"] == "medium"


def test_lift_profile_update_cleans_profiles_and_keeps_known_angles():
    core = importlib.import_module("services.handlers.program.program_update_lift_profiles.core")
    normalized = core.normalize_lift_profiles([{
        "lift": "squat",
        "options": {"bar_position": "low"},
        "failure_nodes": ["hips rise"],
        "form_videos": {"front": {"video_id": "front-1"}, "rear": {"video_id": "ignored"}},
    }, {"lift": "curl"}])
    assert len(normalized) == 1
    assert normalized[0]["options"] == {"bar_position": "low"}
    assert normalized[0]["notes"] == ""
    assert list(normalized[0]["form_videos"]) == ["front"]


def test_exercise_ai_fallbacks_match_runtime_schemas(monkeypatch):
    operations = load_operations("lift-profiles")
    for name in ("fatigue_profile_estimate", "muscle_group_estimate"):
        core = importlib.import_module(
            f"services.handlers.lift_profiles.{name}.core"
        )

        class FakeStore:
            async def get_program(self):
                return {}

        monkeypatch.setattr(core, "_get_program_store", lambda: FakeStore())
        result = dispatch(operations[name], {"exercise": {"name": "squat"}})
        operations[name].validate_result(result)


def test_glossary_fatigue_handler_keeps_storage_update(monkeypatch):
    core = importlib.import_module(
        "services.handlers.lift_profiles.glossary_estimate_fatigue.core"
    )
    ai = importlib.import_module(
        "services.handlers.lift_profiles.glossary_estimate_fatigue.fatigue_ai"
    )

    class GlossaryStore:
        def __init__(self):
            self.updated = None

        async def get_glossary(self):
            return [{"id": "squat", "name": "Squat"}]

        async def update_exercise(self, exercise_id, fields):
            self.updated = (exercise_id, fields)

    class ProgramStore:
        async def get_program(self):
            return {"meta": {}, "lift_profiles": []}

    glossary = GlossaryStore()
    monkeypatch.setattr(core, "_get_glossary_store", lambda *args: glossary)
    monkeypatch.setattr(core, "_get_program_store", lambda *args: ProgramStore())

    async def fake_estimate(*args, **kwargs):
        return {"axial": 0.2, "neural": 0.3, "peripheral": 0.4, "systemic": 0.5, "reasoning": "test"}

    monkeypatch.setattr(ai, "estimate_fatigue_profile", fake_estimate)
    result = core.glossary_estimate_fatigue({"id": "squat"})
    assert result["status"] == "fatigue_estimated"
    assert glossary.updated == (
        "squat",
        {
            "fatigue_profile": {"axial": 0.2, "neural": 0.3, "peripheral": 0.4, "systemic": 0.5},
            "fatigue_profile_source": "ai_estimated",
            "fatigue_profile_reasoning": "test",
        },
    )
