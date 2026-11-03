import importlib
from datetime import date

import pytest


@pytest.mark.parametrize("module_name", [
    "services.handlers.competition.health_complete_competition.analytics",
    "services.handlers.competition.health_snapshot_competition_projection.analytics",
    "services.handlers.program.export_program_history.analytics",
    "services.handlers.program.export_program_markdown.analytics",
])
def test_analytics_copies_suggest_e1rm_multipliers(module_name):
    analytics = importlib.import_module(module_name)
    program = {"sessions": [], "competitions": [], "lift_profiles": [{"lift": "squat", "e1rm_multiplier": 1.05}]}
    result = analytics.compute_e1rm_multiplier_suggestions(program, [], date(2026, 10, 23))
    assert isinstance(result, dict)
    assert analytics._lift_e1rm_multipliers(program["lift_profiles"]) == {"squat": 1.05, "bench": 1.0, "deadlift": 1.0}
