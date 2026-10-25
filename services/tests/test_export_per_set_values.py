import importlib
from decimal import Decimal

import pytest
from openpyxl import Workbook

from services.lib.performed_sets import expand_performed_sets, expand_session_sets

BENCH = {
    "id": "bench", "name": "Bench Press", "sets": 3, "reps": 6, "kg": 83.915, "rpe": 9, "notes": "first set heavy",
    "set_statuses": ["completed", "completed", "completed"], "failed_sets": [False, False, False], "failed_set_reasons": [[], [], []],
    "sets_data": [
        {"kg": 83.915, "rpe": 9, "reps": 6},
        {"kg": 86.183, "rpe": 8, "reps": 6},
        {"kg": 74.843, "rpe": Decimal("8.5"), "reps": 6},
    ],
}
PUSHDOWN = {
    "id": "push", "name": "Triceps Pushdown", "sets": 2, "reps": 10, "kg": 36.287, "rpe": 10,
    "set_statuses": ["completed", "failed"], "failed_sets": [False, True], "failed_set_reasons": [[], ["strength_failure"]],
    "sets_data": [{"kg": 36.287, "rpe": 10, "reps": 10}, {"kg": 27.216, "rpe": 9.5, "reps": 8}],
}
RDL = {
    "id": "rdl", "name": "Romanian Deadlift", "sets": 2, "reps": 8, "kg": 80, "rpe": 9,
    "set_statuses": ["completed", "completed"], "failed_sets": [False, False],
    "sets_data": [{"kg": 83.915, "rpe": 8.5, "reps": 8}, {"kg": 83.915, "rpe": 8.5, "reps": 8}],
}
SESSION = {"date": "2026-10-19", "week_number": 3, "block": "current", "status": "completed", "exercises": [BENCH, PUSHDOWN, RDL]}
MODULES = ["services.handlers.program.export_program_history.export", "services.handlers.program.export_program_markdown.export"]


def test_varied_sets_become_one_row_per_set_with_their_own_values():
    rows = expand_performed_sets(BENCH)
    assert [(r["set_number"], r["sets"], r["reps"], r["kg"], r["rpe"]) for r in rows] == [(1, 1, 6, 83.915, 9), (2, 1, 6, 86.183, 8), (3, 1, 6, 74.843, 8.5)]
    assert rows[0]["notes"] == "first set heavy" and rows[1]["notes"] == ""
    assert all("sets_data" not in r for r in rows)


def test_each_set_keeps_its_status_and_failure():
    first, second = expand_performed_sets(PUSHDOWN)
    assert (first["failed"], first["set_statuses"]) == (False, ["completed"])
    assert (second["failed"], second["failed_sets"], second["failed_set_reasons"], second["set_statuses"], second["rpe"]) == (True, [True], [["strength_failure"]], ["failed"], 9.5)


def test_identical_sets_stay_straight_with_per_set_values():
    (row,) = expand_performed_sets(RDL)
    assert (row["sets"], row["reps"], row["kg"], row["rpe"]) == (2, 8, 83.915, 8.5)


def test_exercises_without_per_set_data_are_unchanged():
    legacy = {"name": "Squat", "sets": 3, "reps": 5, "kg": 140, "rpe": 8.5}
    assert expand_performed_sets(legacy) == [legacy]


@pytest.mark.parametrize("module_name", MODULES)
def test_markdown_lists_every_varied_set(module_name):
    export = importlib.import_module(module_name)
    text = export._md_sessions(expand_session_sets([SESSION]))
    for row in ("| Bench Press | 1 x 6 | 83.915 | 9 |", "| Bench Press | 1 x 6 | 86.183 | 8 |", "| Bench Press | 1 x 6 | 74.843 | 8.5 |",
                "| Triceps Pushdown | 1 x 8 | 27.216 | 9.5 |", "| Romanian Deadlift | 2 x 8 | 83.915 | 8.5 |"):
        assert row in text, row


@pytest.mark.parametrize("module_name", MODULES)
def test_excel_lists_every_varied_set(module_name):
    export = importlib.import_module(module_name)
    getattr(export, "_ensure_excel", lambda: None)()
    wb = Workbook()
    export._write_exercises_sheet(wb, expand_session_sets([SESSION]))
    rows = [[cell.value for cell in row] for row in wb["Exercises"].iter_rows(min_row=2)]
    assert [(row[4], row[5], row[6], row[7], row[11]) for row in rows] == [
        ("Bench Press", 1, 6, 83.915, 9), ("Bench Press", 1, 6, 86.183, 8), ("Bench Press", 1, 6, 74.843, 8.5),
        ("Triceps Pushdown", 1, 10, 36.287, 10), ("Triceps Pushdown", 1, 8, 27.216, 9.5),
        ("Romanian Deadlift", 2, 8, 83.915, 8.5),
    ]
