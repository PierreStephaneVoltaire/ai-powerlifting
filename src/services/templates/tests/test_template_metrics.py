from datetime import date

from services.templates.template_evaluate.metrics import competition_lift, load_mode, strip_calendar, template_metrics, template_program
from services.templates.template_evaluate import metrics as metrics_module

GLOSSARY = [
    {"id": "g-squat", "name": "Squat", "category": "squat", "fatigue_category": "primary_axial", "primary_muscles": ["quads", "glutes"], "secondary_muscles": ["lower_back"], "tertiary_muscles": ["abs"], "fatigue_profile": {"axial": 0.9, "neural": 0.8, "peripheral": 0.6, "systemic": 0.7}},
    {"id": "g-pause", "name": "Pause Bench Press", "category": "bench", "e1rm_estimate": {"value_kg": 115}, "primary_muscles": ["chest"], "fatigue_profile": {"axial": 0.1, "neural": 0.5, "peripheral": 0.5, "systemic": 0.3}},
    {"id": "g-row", "name": "Pendlay Row", "category": "back", "primary_muscles": ["lats"], "fatigue_profile": {"axial": 0.4, "neural": 0.3, "peripheral": 0.5, "systemic": 0.3}},
]


def template(weeks):
    return {
        "meta": {"name": "Peak", "description": "parser notes", "program_context": "overreach", "author_pk": "p1"},
        "phases": [{"name": "build", "week_start": 1, "week_end": 1}, {"name": "peak", "week_start": 2, "week_end": 2}],
        "sessions": [{"date": "2027-01-02", "id": "s", "week_number": week, "day_of_week": "Saturday", "exercises": exercises} for week, exercises in weeks],
    }


def test_competition_lift_recognizes_prescription_rows_but_not_variations():
    assert competition_lift("Squat heavy single") == "squat"
    assert competition_lift("Bench light backoff") == "bench"
    assert competition_lift("Deadlift test single") == "deadlift"
    assert competition_lift("Pause bench") is None
    assert competition_lift("Snatch deadlift") is None


def test_unprescribed_loads_count_as_user_selected_rpe_8():
    assert load_mode({"load_type": "unresolvable"}) == ("user_selected", 8.0)
    assert load_mode({"name": "Dead bug"}) == ("user_selected", 8.0)
    assert load_mode({"load_type": "rpe", "load_value": "7"}) == ("rpe", 7.0)
    assert load_mode({"load_type": "absolute", "load_value": "162.5"}) == ("absolute", 162.5)


def test_template_report_runs_the_app_analysis_on_the_template_alone_with_current_maxes(monkeypatch):
    weeks = [
        (1, [{"name": "Squat heavy single", "sets": 1, "reps": 1, "load_type": "absolute", "load_value": 162.5},
             {"name": "Pendlay Row", "sets": 3, "reps": 5, "load_type": "unresolvable"}]),
        (2, [{"name": "Squat heavy single", "sets": 2, "reps": 1, "load_type": "absolute", "load_value": 185},
             {"name": "Pause Bench Press", "sets": 2, "reps": 4, "load_type": "percentage", "load_value": 80}]),
    ]
    calls = []

    def weekly_analysis(program, sessions, **params):
        calls.append((program, sessions, params))
        return {"current_maxes": {"method": "provided", "squat": 185}, "inol": {}, "compliance": {}, "readiness_score": 1, "projections": []}

    monkeypatch.setattr(metrics_module.analytics_client, "weekly_analysis", weekly_analysis)
    result = template_metrics(template(weeks), GLOSSARY, {"squat": 185, "bench": 122.5})
    analysis = result["analysis"]
    assert result["weeks"] == 2
    assert calls[0][2]["current_maxes"] == {"squat": 185.0, "bench": 122.5}
    assert (calls[0][2]["week_start"], calls[0][2]["week_end"], calls[0][2]["block"]) == (1, 2, "")
    assert analysis["current_maxes"]["squat"] == 185 and "inol" in analysis
    assert not {"compliance", "readiness_score", "selected_session_context", "projections"} & set(analysis)
    assert result["template"]["top_set_pct_of_current_max_by_week"] == {"1": {"squat": 87.8}, "2": {"squat": 100.0}}
    assert result["template"]["exercises"]["Pause Bench Press"]["planned_load_sources"] == ["percent_of_e1rm"]
    assert result["template"]["exercises"]["Pause Bench Press"]["role"] == "variation"
    assert result["template"]["load_not_computable"] == ["Pendlay Row"]


def test_template_program_dates_follow_week_and_weekday_without_logged_history():
    weeks = [(1, [{"name": "Squat", "sets": 1, "reps": 1, "load_type": "absolute", "load_value": 150}]),
             (2, [{"name": "Squat", "sets": 1, "reps": 1, "load_type": "absolute", "load_value": 155}])]
    program, _ = template_program(template(weeks), GLOSSARY, {"squat": 185}, [])
    first, second = (date.fromisoformat(session["date"]) for session in program["sessions"])
    assert first.weekday() == 5 and (second - first).days == 7
    assert program["competitions"] == [] and program["current_maxes"] == {"squat": 185.0}


def test_strip_calendar_removes_dates_and_keeps_only_design_meta():
    stripped = strip_calendar(template([(1, [])]))
    assert "date" not in stripped["sessions"][0] and "id" not in stripped["sessions"][0]
    assert stripped["meta"] == {"name": "Peak", "program_context": "overreach"}
