import importlib
import json

import httpx
import pytest


from services.contract import load_operations
from services.dispatch import dispatch


def _profile():
    return {
        "lift": "squat",
        "style_notes": "High bar stance with competition depth, bracing, and controlled eccentric.",
        "sticking_points": "Slow out of the hole with a forward torso shift and speed loss.",
        "primary_muscle": "Quads are the primary driver and limiting muscle.",
        "volume_tolerance": "moderate",
    }


def test_lift_profile_contracts_describe_all_outputs():
    operations = load_operations("lift-profiles")
    assert list(operations) == [
        "fatigue_profile_estimate",
        "muscle_group_estimate",
        "lift_profile_estimate_stimulus",
        "lift_profile_review",
        "lift_profile_rewrite",
        "lift_profile_rewrite_and_estimate",
        "program_update_lift_profiles",
    ]
    assert all(operation.result_schema for operation in operations.values())
    for operation in operations.values():
        with pytest.raises(Exception):
            operation.validate_input({})


def test_review_dispatch_uses_native_runtime_completion(monkeypatch):
    module = __import__(
        "services.handlers.lift_profiles.lift_profile_review.lift_profile_ai",
        fromlist=["completion"],
    )

    async def fake_completion(payload):
        assert payload["tools"][0]["function"]["name"] == "review_lift_profile"
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "function": {
                                "arguments": json.dumps({
                                    "completeness_score": 90,
                                    "ready_for_coefficient": True,
                                    "missing_details": [],
                                    "suggestions": ["Keep tracking bar path."],
                                })
                            }
                        }]
                    }
                }]
            },
            request=httpx.Request("POST", "http://fake"),
        )

    monkeypatch.setattr(module, "completion", fake_completion)
    operation = load_operations("lift-profiles")["lift_profile_review"]
    result = dispatch(operation, {"profile": _profile()})
    operation.validate_result(result)
    assert result["suggestions"] == ["Keep tracking bar path."]


def test_estimate_fallback_keeps_profile_result_shape():
    operation = load_operations("lift-profiles")["lift_profile_estimate_stimulus"]
    result = dispatch(operation, {"profile": {"lift": "squat"}})
    operation.validate_result(result)
    assert result["stimulus_coefficient"] == 1.0
    assert result["ready_for_estimate"] is False


def test_lift_profile_update_normalizes_failure_nodes_and_angles():
    core = importlib.import_module(
        "services.handlers.program.program_update_lift_profiles.core"
    )
    normalized = core.normalize_lift_profiles([{
        "lift": "squat",
        "failure_nodes": ["  hips rise  ", "HIPS RISE", "x" * 200] * 4,
        "form_videos": {
            "front": {"video_id": "front-1"},
            "rear": {"video_id": "ignored"},
        },
    }])
    assert normalized[0]["failure_nodes"] == ["hips rise", "x" * 160]
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
