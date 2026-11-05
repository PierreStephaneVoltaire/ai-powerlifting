import importlib
import json

import pytest
from datetime import date

from services.contract import load_operations
from services.dispatch import dispatch


def test_all_calculations_dispatch_to_actual_handlers():
    operations = load_operations("calculations")
    assert dispatch(operations["lb_to_kg"], {"lb": 220.462}) == {"lb": 220.462, "kg": 100.0}
    assert dispatch(operations["kg_to_lb"], {"kg": 100}) == {"kg": 100, "lb": 220.5}
    assert dispatch(operations["pct_of_max"], {"max_kg": 185, "pct": 85}) == {
        "max_kg": 185,
        "pct": 85,
        "raw_kg": 157.25,
        "rounded_2_5_kg": 157.5,
        "lb": 346.7,
    }
    assert dispatch(operations["ipf_weight_classes"], {"sex": "F"})["classes_kg"][-1] == "84+"
    assert dispatch(operations["calculate_dots"], {"total_kg": 0, "bodyweight_kg": 80, "sex": "male"}) == {"dots": 0.0}
    assert dispatch(operations["estimate_1rm"], {"weight_kg": 100, "reps": 5, "rpe": 8}) == {
        "e1rm": 122.7,
        "method": "rpe_table",
        "input_weight_kg": 100.0,
        "epley": None,
        "brzycki": None,
        "rpe_based": 122.7,
    }

    days = dispatch(operations["days_until"], {"target_date": date.today().isoformat(), "label": "meet"})
    assert days["target_date"] == date.today().isoformat()
    assert days["label"] == "meet"
    assert days["is_past"] is False


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("lb_to_kg", {"lb": 0}),
        ("kg_to_lb", {"kg": 0}),
        ("pct_of_max", {"max_kg": 100, "pct": 0}),
        ("pct_of_max", {"max_kg": 100, "pct": 151}),
        ("calculate_dots", {"total_kg": 100, "bodyweight_kg": 0, "sex": "male"}),
        ("estimate_1rm", {"weight_kg": 100, "reps": 0}),
    ],
)
def test_calculation_bounds_are_rejected(name, arguments):
    with pytest.raises(Exception):
        dispatch(load_operations("calculations")[name], arguments)


def test_handler_returns_json_envelope():
    module = importlib.import_module("services.handlers.calculations.calculate_dots.handler")
    response = module.handler({"args": {"total_kg": 0, "bodyweight_kg": 80, "sex": "male"}}, None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"dots": 0.0}


def test_e1rm_covers_ten_reps_and_treats_a_missing_rpe_as_rpe_ten():
    from services.lib.lift_calculations import estimate_1rm, estimate_1rm_value

    assert round(estimate_1rm_value(100, 8, 9), 2) == round(100 / 0.785, 2)
    assert round(estimate_1rm_value(100, 10, 8), 2) == round(100 / 0.715, 2)
    assert round(estimate_1rm_value(100, 8), 2) == round(100 / 0.82, 2)
    assert estimate_1rm_value(100, 1) == 100
    assert estimate_1rm_value(100, 11) is None
    assert estimate_1rm_value(100, 11, 9) is None
    assert estimate_1rm(100, 6)["method"] == "assumed_rpe_10"
    assert estimate_1rm(100, 6, 8)["method"] == "rpe_table"


def test_every_analytics_copy_estimates_eight_rep_sets_without_rpe():
    import importlib

    for name in (
        "services.handlers.analysis_reports.analytics",
        "services.handlers.program.export_program_markdown.analytics",
        "services.handlers.program.export_program_history.analytics",
        "services.handlers.competition.health_snapshot_competition_projection.analytics",
    ):
        module = importlib.import_module(name)
        sessions = [
            {"date": day, "status": "completed", "session_rpe": rpe, "exercises": [
                {"name": "Squat", "kg": 120, "reps": 8, "sets": 3},
                {"name": "Bench Press", "kg": 85, "reps": 8, "sets": 3},
            ]}
            for day, rpe in (("2026-10-12", 9), ("2026-10-19", None), ("2026-10-26", 8))
        ]
        from datetime import date

        maxes = module._estimate_maxes_from_sessions(sessions, reference_date=date(2026, 11, 2))
        assert set(maxes) == {"squat", "bench"}, name
