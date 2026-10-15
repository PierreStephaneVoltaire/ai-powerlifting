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
