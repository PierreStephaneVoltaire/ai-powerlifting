import importlib

from openpyxl import Workbook

from services.runtime.performed_sets import expand_session_sets


SESSION = {
    "date": "2026-11-16",
    "week_number": 2,
    "block": "current",
    "status": "completed",
    "planned_exercises": [{
        "name": "Squat",
        "sets": 3,
        "reps": 5,
        "kg": 100,
        "rpe_target": 8,
    }],
    "exercises": [{
        "name": "Squat",
        "sets": 3,
        "reps": 5,
        "kg": 95,
        "rpe": 9,
        "sets_data": [
            {"kg": 95, "reps": 5, "rpe": 9},
            {"kg": 97.5, "reps": 5, "rpe": 9.5},
            {"kg": 90, "reps": 5, "rpe": 8},
        ],
        "set_statuses": ["completed", "completed", "completed"],
    }],
}


def test_markdown_shows_planned_and_actual_session_values():
    export = importlib.import_module("services.export.export_program_history.export")
    text = export._md_sessions(expand_session_sets([SESSION]))

    assert "Target RPE" in text
    assert "100" in text and "8" in text
    assert "95" in text and "9" in text
    assert "97.5" in text and "9.5" in text
    assert "90" in text


def test_excel_keeps_planned_and_actual_values_in_their_sheets():
    export = importlib.import_module("services.export.export_program_history.export")
    workbook = Workbook()
    sessions = expand_session_sets([SESSION])

    export._write_planned_exercises_sheet(workbook, sessions)
    export._write_exercises_sheet(workbook, sessions)

    planned = list(workbook["Planned Exercises"].values)
    actual = list(workbook["Exercises"].values)
    assert planned[1][4:10] == ("Squat", 3, 5, 100, "", 8)
    assert [(row[4], row[5], row[6], row[7], row[11]) for row in actual[1:]] == [
        ("Squat", 1, 5, 95, 9),
        ("Squat", 1, 5, 97.5, 9.5),
        ("Squat", 1, 5, 90, 8),
    ]


def test_weekly_e1rm_changes_require_consecutive_weeks_with_the_same_lift():
    export = importlib.import_module("services.export.export_program_history.export")
    sessions = [
        {"week_number": week, "status": "completed", "exercises": [{"name": "Squat", "sets": 1, "reps": 1, "kg": kg, "rpe": 10}]}
        for week, kg in [(1, 100), (2, 110), (4, 120)]
    ]
    rows = export._build_dots_trend_rows(sessions, [], "male")
    assert [row["squat_delta"] for row in rows] == [None, 10, None]
    assert all(row["bench_delta"] is None for row in rows)
    assert "Squat change (kg)" in "\n".join(export._md_dots_trend(rows))
