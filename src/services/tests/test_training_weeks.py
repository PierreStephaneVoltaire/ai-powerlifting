import importlib

import pytest

MODULES = [
    "services.handlers.templates.template_apply.training_weeks",
    "services.handlers.templates.template_apply_confirm.training_weeks",
    "services.handlers.program.health_setup_initialize.training_weeks",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_active_block_week_start_wins_over_stale_current(module_name):
    module = importlib.import_module(module_name)
    program = {"meta": {
        "current_block_id": "block-new",
        "block_week_start_days": {"current": "Saturday", "block-new": "Sunday", "old": "Saturday"},
    }}
    assert module.week_start_for_block(program) == "Sunday"
    assert module.week_start_for_block(program, "old") == "Saturday"


@pytest.mark.parametrize("module_name", MODULES)
def test_week_start_falls_back_through_block_record_current_and_program_default(module_name):
    module = importlib.import_module(module_name)
    assert module.week_start_for_block({"meta": {"blocks": [{"id": "b1", "status": "active", "week_start_day": "Tuesday"}]}}) == "Tuesday"
    assert module.week_start_for_block({"meta": {"block_week_start_days": {"current": "friday"}}}) == "Friday"
    assert module.week_start_for_block({"meta": {"program_week_start_day": "Wednesday"}}) == "Wednesday"
    assert module.week_start_for_block({"meta": {}}) == "Monday"
