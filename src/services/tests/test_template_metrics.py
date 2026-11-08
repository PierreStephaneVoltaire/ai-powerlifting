from services.handlers.templates.template_evaluate.metrics import competition_lift, load_mode, strip_calendar, template_metrics

GLOSSARY = [
    {"id": "g-squat", "name": "Squat", "category": "squat", "fatigue_category": "primary_axial", "primary_muscles": ["quads", "glutes"], "secondary_muscles": ["lower_back"], "tertiary_muscles": ["abs"], "fatigue_profile": {"axial": 0.9, "neural": 0.8, "peripheral": 0.6, "systemic": 0.7}},
    {"id": "g-pause", "name": "Pause Bench Press", "category": "bench", "primary_muscles": ["chest"], "fatigue_profile": {"axial": 0.1, "neural": 0.5, "peripheral": 0.5, "systemic": 0.3}},
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


def test_weekly_metrics_cover_specificity_muscles_fatigue_and_main_lift_intensity():
    weeks = [
        (1, [{"name": "Squat heavy single", "sets": 1, "reps": 1, "load_type": "absolute", "load_value": 162.5},
             {"name": "Pendlay Row", "sets": 3, "reps": 5, "load_type": "unresolvable"}]),
        (2, [{"name": "Squat heavy single", "sets": 2, "reps": 1, "load_type": "absolute", "load_value": 185},
             {"name": "Pause Bench Press", "sets": 2, "reps": 4, "load_type": "rpe", "load_value": 8}]),
    ]
    result = template_metrics(template(weeks), GLOSSARY, {"squat": 185, "bench": 122.5}, lambda weeks_out: {"narrow": {"min": 0.5}, "broad": {"min": 0.7}})
    first, second = result["weekly"]
    assert result["weeks"] == 2
    assert first["specificity_narrow"] == 0.25 and second["specificity_narrow"] == 0.5 and second["specificity_broad"] == 1.0
    assert first["main_lifts"]["squat"]["top_set_pct_of_current_max"] == 87.8
    assert second["main_lifts"]["squat"]["top_set_pct_of_current_max"] == 100.0
    assert first["weeks_before_final_week"] == 1 and second["expected_specificity_band"]["narrow"] == {"min": 0.5}
    assert result["avg_weighted_sets_per_muscle_per_week"]["build"] == {"lats": 3.0, "glutes": 1.0, "quads": 1.0, "lower_back": 0.5, "abs": 0.25}
    assert first["fatigue_vs_week_1"]["axial"] == 1.0 and second["fatigue_vs_week_1"]["axial"] > 1.0
    assert result["exercises"]["Pendlay Row"]["load_modes"] == ["user_selected"]
    assert result["exercises"]["Squat heavy single"]["role"] == "competition_lift"
    assert result["exercises"]["Pause Bench Press"]["role"] == "variation"


def test_strip_calendar_removes_dates_and_keeps_only_design_meta():
    stripped = strip_calendar(template([(1, [])]))
    assert "date" not in stripped["sessions"][0] and "id" not in stripped["sessions"][0]
    assert stripped["meta"] == {"name": "Peak", "program_context": "overreach"}
