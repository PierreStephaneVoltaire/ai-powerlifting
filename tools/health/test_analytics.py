from __future__ import annotations

import asyncio
import copy
import math
import sys
import types
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analytics  # noqa: E402
import core  # noqa: E402
import template_apply  # noqa: E402


TODAY = date(2026, 4, 24)


class FrozenDate(date):
    @classmethod
    def today(cls) -> "FrozenDate":
        return cls(TODAY.year, TODAY.month, TODAY.day)


@pytest.fixture(autouse=True)
def freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analytics, "date", FrozenDate)


def test_save_program_version_converts_nested_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeTable:
        def put_item(self, Item: dict) -> None:
            captured["item"] = Item

    class FakeStore:
        def invalidate_cache(self) -> None:
            captured["invalidated"] = True

    monkeypatch.setattr(core, "_get_table_and_pk", lambda: (FakeTable(), "operator", FakeStore()))
    fake_cache_module = types.ModuleType("cache_invalidation")
    fake_cache_module.invalidate_analysis_caches = lambda *args, **kwargs: captured.__setitem__(
        "cache_invalidated",
        args,
    )
    monkeypatch.setitem(sys.modules, "cache_invalidation", fake_cache_module)

    core._save_program_version(
        {
            "sessions": None,
            "competitions": [
                {
                    "date": "2025-10-04",
                    "actual_body_weight_kg": 82.5,
                    "post_meet_report": {"sleep_hours": 6.5, "attempt_selection_grade": 8.5},
                }
            ],
        },
        "program#v001",
    )

    item = captured["item"]
    assert isinstance(item, dict)
    competition = item["competitions"][0]
    assert isinstance(competition["actual_body_weight_kg"], Decimal)
    assert isinstance(competition["post_meet_report"]["sleep_hours"], Decimal)
    assert isinstance(competition["post_meet_report"]["attempt_selection_grade"], Decimal)
    assert item["pk"] == "operator"
    assert item["sk"] == "program#v001"
    assert captured["invalidated"] is True
    assert captured["cache_invalidated"][0] == "operator"


def make_exercise(name: str, kg: float, reps: int, sets: int = 1, **extra) -> dict:
    exercise = {
        "name": name,
        "kg": kg,
        "reps": reps,
        "sets": sets,
    }
    exercise.update(extra)
    return exercise


def make_session(
    days_ago: int,
    exercises: list[dict],
    *,
    session_rpe: float | None = None,
    week_number: int | None = None,
    body_weight_kg: float | None = None,
    wellness: dict | None = None,
    status: str = "completed",
    completed: bool = True,
) -> dict:
    d = TODAY - timedelta(days=days_ago)
    session = {
        "date": d.isoformat(),
        "week_number": week_number if week_number is not None else max(1, days_ago // 7 + 1),
        "completed": completed,
        "status": status,
        "session_rpe": session_rpe,
        "exercises": exercises,
    }
    if body_weight_kg is not None:
        session["body_weight_kg"] = body_weight_kg
    if wellness is not None:
        session["wellness"] = wellness
    return session


def make_wellness(sleep: int, soreness: int, mood: int, stress: int, energy: int) -> dict:
    return {
        "sleep": sleep,
        "soreness": soreness,
        "mood": mood,
        "stress": stress,
        "energy": energy,
        "recorded_at": TODAY.isoformat(),
    }


def make_sbd_session(
    days_ago: int,
    squat_kg: float,
    bench_kg: float,
    deadlift_kg: float,
    *,
    session_rpe: float,
    week_number: int | None = None,
    completed: bool = True,
) -> dict:
    return make_session(
        days_ago,
        [
            make_exercise("Squat", squat_kg, 1),
            make_exercise("Bench Press", bench_kg, 1),
            make_exercise("Deadlift", deadlift_kg, 1),
        ],
        session_rpe=session_rpe,
        week_number=week_number,
        completed=completed,
    )


def test_fatigue_index_resets_streak_on_skipped_week() -> None:
    # 5 weeks of heavy training
    sessions = []
    for week_idx in range(1, 6):
        for day in range(3):
            sessions.append(
                make_session(
                    (6 - week_idx) * 7 + day,
                    [make_exercise("Squat", 200, 5, sets=5)],
                    session_rpe=10,
                    week_number=week_idx
                )
            )
    
    program_start = (TODAY - timedelta(days=42)).isoformat()
    
    # Check streak at week 5
    fi_w5 = analytics.fatigue_index(sessions, program_start=program_start, ref_date=TODAY, days=60)
    # week 5 is index 5
    w5_data = next(f for wk, f in fi_w5["weekly_fis"] if wk == 5)
    assert w5_data["components"]["overload_streak"] > 0
    
    # Now skip week 6
    # week 7 has training again
    for day in range(3):
        sessions.append(
            make_session(
                -7 + day, 
                [make_exercise("Squat", 200, 5, sets=5)],
                session_rpe=10,
                week_number=7
            )
        )
    
    # Week 6 is missing (skipped)
    # The streak should reset at week 6 and be low at week 7
    ref_future = TODAY + timedelta(days=14)
    fi_w7 = analytics.fatigue_index(sessions, program_start=program_start, ref_date=ref_future, days=60)
    
    w6_data = next(f for wk, f in fi_w7["weekly_fis"] if wk == 6)
    w7_data = next(f for wk, f in fi_w7["weekly_fis"] if wk == 7)
    
    assert w6_data["components"]["overload_streak"] == 0
    assert w7_data["components"]["overload_streak"] == 0.25 # Streak starts over


def test_fatigue_physics_is_nonlinear() -> None:
    profile = {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}

    neural_90 = analytics._per_set_fatigue(180, 1, profile, 200)["neural"]
    neural_95 = analytics._per_set_fatigue(190, 1, profile, 200)["neural"]
    axial_70x3 = analytics._per_set_fatigue(140, 3, profile, 200)["axial"]
    axial_90x3 = analytics._per_set_fatigue(180, 3, profile, 200)["axial"]
    systemic_70 = analytics._per_set_fatigue(140, 1, profile, 200)["systemic"]
    systemic_90 = analytics._per_set_fatigue(180, 1, profile, 200)["systemic"]

    assert neural_95 > neural_90
    assert axial_90x3 > axial_70x3
    assert systemic_90 > systemic_70


def test_set_statuses_drive_executed_volume_and_failures() -> None:
    exercise = make_exercise(
        "Squat",
        100,
        5,
        sets=4,
        set_statuses=["completed", "failed", "skipped", "pending"],
        failed_sets=[False, False, False, False],
        failed_set_reasons=[[], ["grip", "lockout"], [], []],
    )

    assert analytics._executed_sets(exercise) == 2
    assert analytics._executed_volume(exercise) == 1000
    assert analytics._count_failed_sets(exercise) == 1


def test_set_statuses_fallback_to_legacy_failed_sets() -> None:
    exercise = make_exercise("Bench Press", 80, 5, sets=3, failed_sets=[False, True, False])

    assert analytics._executed_sets(exercise) == 3
    assert analytics._count_failed_sets(exercise) == 1


@pytest.mark.parametrize(
    ("avg_rpe", "expected"),
    [
        (7.5, 0.0),
        (8.0, 0.2),
        (8.5, 0.4),
        (9.0, 0.6),
        (9.5, 0.8),
        (10.0, 1.0),
    ],
)
def test_fatigue_index_rpe_stress_mapping(avg_rpe: float, expected: float) -> None:
    sessions = [
        make_session(1, [make_exercise("Squat", 100, 1)], session_rpe=avg_rpe),
        make_session(0, [make_exercise("Squat", 100, 1)], session_rpe=avg_rpe),
    ]

    result = analytics.fatigue_index(sessions, days=14)

    assert result["components"]["rpe_stress"] == pytest.approx(expected, abs=1e-3)
    assert result["score"] == pytest.approx(expected * 0.15, abs=1e-3)


def test_progression_rate_returns_fit_metrics() -> None:
    sessions = [
        make_session(21, [make_exercise("Squat", 100, 1)], session_rpe=10, week_number=1),
        make_session(14, [make_exercise("Squat", 110, 1)], session_rpe=10, week_number=2),
        make_session(7, [make_exercise("Squat", 120, 1)], session_rpe=10, week_number=3),
    ]

    result = analytics.progression_rate(sessions, "Squat", "2026-03-01")

    assert result["slope_kg_per_week"] == pytest.approx(10.0, abs=1e-6)
    assert result["kendall_tau"] == pytest.approx(1.0, abs=1e-6)
    assert result["fit_quality"] == pytest.approx(1.0, abs=1e-6)
    assert result["r2"] == pytest.approx(1.0, abs=1e-6)
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-6)


def test_exercise_stats_ignores_skipped_sets() -> None:
    # Exercise with 1 completed set at 200kg and 1 skipped set at 231kg
    ex = make_exercise("Deadlift", 200, 1)
    ex["set_statuses"] = ["completed", "skipped"]
    ex["sets"] = 2
    # In this case, 'kg' in exercise usually refers to the intended load.
    # If the user performed 200 and skipped 231, they might have updated the exercise kg to 231
    # but only completed the first set at a lower weight or intended to do 231 but skipped it.
    # Usually, 'kg' is the actual load for the executed sets.
    # Let's simulate the scenario where kg=231 is in the exercise but the executed sets don't count it.
    ex_skipped = {
        "name": "Deadlift",
        "kg": 231,
        "reps": 1,
        "sets": 1,
        "set_statuses": ["skipped"]
    }
    ex_completed = {
        "name": "Deadlift",
        "kg": 200,
        "reps": 1,
        "sets": 1,
        "set_statuses": ["completed"]
    }

    program = {
        "meta": {"program_start": "2026-04-01"},
        "phases": [],
        "sessions": [],
    }
    sessions = [
        {
            "date": "2026-04-15",
            "week_number": 3,
            "completed": True,
            "status": "completed",
            "exercises": [ex_completed, ex_skipped]
        }
    ]

    result = analytics.weekly_analysis(program, sessions, ref_date="2026-04-15")

    # The max_kg should be 200, not 231
    assert result["exercise_stats"]["Deadlift"]["max_kg"] == 200
    assert result["exercise_stats"]["Deadlift"]["total_sets"] == 1
    # Check lifts report as well
    assert result["lifts"]["deadlift"]["max_kg"] == 200


def test_estimate_maxes_from_comps_ignores_skipped_status() -> None:
    competitions = [
        {
            "name": "Skipped Meet",
            "date": "2026-05-01",
            "status": "skipped",
            "results": {
                "squat_kg": 300,
                "bench_kg": 200,
                "deadlift_kg": 350,
            }
        },
        {
            "name": "Real Meet",
            "date": "2026-04-01",
            "status": "completed",
            "results": {
                "squat_kg": 200,
                "bench_kg": 100,
                "deadlift_kg": 250,
            }
        }
    ]
    
    # Should pick Real Meet results, not Skipped Meet
    maxes = analytics._estimate_maxes_from_comps(competitions, reference_date=date(2026, 5, 10))
    assert maxes["squat"] == 200
    assert maxes["bench"] == 100
    assert maxes["deadlift"] == 250


def test_rpe_drift_returns_fit_metrics() -> None:
    sessions = [
        make_session(21, [make_exercise("Squat", 100, 1)], session_rpe=7, week_number=1),
        make_session(14, [make_exercise("Squat", 100, 1)], session_rpe=8, week_number=2),
        make_session(7, [make_exercise("Squat", 100, 1)], session_rpe=9, week_number=3),
    ]

    result = analytics.rpe_drift(sessions, "Squat", "2026-03-01")

    assert result["slope"] == pytest.approx(1.0, abs=1e-6)
    assert result["kendall_tau"] == pytest.approx(1.0, abs=1e-6)
    assert result["fit_quality"] == pytest.approx(1.0, abs=1e-6)
    assert result["r2"] == pytest.approx(1.0, abs=1e-6)
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-6)


def test_compute_inol_uses_per_lift_thresholds_and_smoothing() -> None:
    sessions = [
        make_session(
            0,
            [
                make_exercise("Squat", 120, 10, 10),
                make_exercise("Bench Press", 120, 10, 10),
                make_exercise("Deadlift", 80, 5, 5),
            ],
        )
    ]
    lift_profiles = [
        {
            "lift": "squat",
            "stimulus_coefficient": 1.0,
            "inol_low_threshold": 0.1,
            "inol_high_threshold": 0.2,
        }
    ]

    result = analytics.compute_inol(
        sessions,
        program_start=TODAY.isoformat(),
        current_maxes={"squat": 200, "bench": 200, "deadlift": 200},
        lift_profiles=lift_profiles,
    )

    assert result["avg_inol"]["squat"] == pytest.approx(2.50, abs=0.02)
    assert result["avg_inol"]["bench"] == pytest.approx(2.50, abs=0.02)
    assert result["avg_inol"]["deadlift"] == pytest.approx(0.42, abs=0.02)
    assert result["thresholds"]["squat"] == {"low": 0.1, "high": 0.2}
    assert result["thresholds"]["bench"] == {"low": 2.0, "high": 5.0}
    assert result["thresholds"]["deadlift"] == {"low": 1.0, "high": 2.5}
    assert "overreaching_risk_squat" in result["flags"]
    assert "low_stimulus_deadlift" in result["flags"]
    assert "overreaching_risk_bench" not in result["flags"]
    assert "low_stimulus_bench" not in result["flags"]


def test_compute_acwr_daily_ewma_and_labels() -> None:
    sessions: list[dict] = []
    for day_index in range(35):
        days_ago = 34 - day_index
        kg = 50 if day_index < 28 else 300
        sessions.append(
            make_session(
                days_ago,
                [make_exercise("Squat", kg, 1)],
                week_number=day_index // 7 + 1,
            )
        )

    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        }
    ]

    result = analytics.compute_acwr(
        sessions,
        glossary=glossary,
        program_start=(TODAY - timedelta(days=34)).isoformat(),
        current_maxes={"squat": 300},
        phases=[
            {
                "name": "Overreach",
                "intent": "planned overreach block",
                "start_week": 1,
                "end_week": 8,
                "target_rpe_max": 9,
            }
        ],
        current_week=5,
        ref_date=TODAY,
    )

    assert result["composite_zone"] == "load_spike"
    assert result["composite_label"] == "Load spike (expected during planned overreach)"
    assert result["dimensions"]["axial"]["zone"] == "load_spike"
    assert result["dimensions"]["axial"]["label"] == "Load spike (expected during planned overreach)"
    assert result["dimensions"]["neural"]["label"].endswith("(expected during planned overreach)")
    assert math.isfinite(result["composite"])


def test_weekly_analysis_respects_requested_window() -> None:
    sessions = [
        make_session(
            83 - (idx * 7),
            [
                make_exercise("Squat", 100, 1),
                make_exercise("Bench Press", 80, 1),
                make_exercise("Deadlift", 120, 1),
            ],
            week_number=idx + 1,
        )
        for idx in range(12)
    ]
    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=83)).isoformat(),
            "block_week_start_days": {"current": "Saturday"},
        },
        "phases": [],
        "competitions": [],
    }
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Bench Press",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Deadlift",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
    ]

    result_4 = analytics.weekly_analysis(program, sessions, weeks=4, block="current", glossary=glossary)
    result_8 = analytics.weekly_analysis(program, sessions, weeks=8, block="current", glossary=glossary)
    result_12 = analytics.weekly_analysis(program, sessions, weeks=12, block="current", glossary=glossary)

    assert result_4["sessions_analyzed"] == 4
    assert result_4["compliance"]["planned"] == 4
    assert result_4["compliance"]["completed"] == 4

    assert result_8["sessions_analyzed"] == 8
    assert result_8["compliance"]["planned"] == 8
    assert result_8["compliance"]["completed"] == 8

    assert result_12["sessions_analyzed"] == 12
    assert result_12["compliance"]["planned"] == 12
    assert result_12["compliance"]["completed"] == 12


def test_compute_acwr_requires_25_calendar_days() -> None:
    sessions = [
        make_session(
            days_ago,
            [make_exercise("Squat", 100, 1)],
        )
        for days_ago in range(23, -1, -1)
    ]

    result = analytics.compute_acwr(
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=(TODAY - timedelta(days=23)).isoformat(),
        current_maxes={"squat": 200},
        ref_date=TODAY,
    )

    assert result["status"] == "insufficient_data"
    assert "25 calendar days" in result["reason"]


def test_compute_acwr_accepts_25_calendar_days() -> None:
    sessions = [
        make_session(
            days_ago,
            [make_exercise("Squat", 100, 1)],
        )
        for days_ago in range(24, -1, -1)
    ]

    result = analytics.compute_acwr(
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=(TODAY - timedelta(days=24)).isoformat(),
        current_maxes={"squat": 200},
        ref_date=TODAY,
    )

    assert "status" not in result
    assert result["composite"] is not None
    assert math.isfinite(result["composite"])


def test_weekly_analysis_previous_week_window_excludes_current_week() -> None:
    program = {
        "meta": {"program_start": "2026-04-01"},
        "phases": [],
        "sessions": [],
    }
    sessions = [
        make_session(9, [make_exercise("Squat", 100, 1)], week_number=2),
        make_session(2, [make_exercise("Squat", 110, 1)], week_number=3),
    ]

    result = analytics.weekly_analysis(
        program,
        sessions,
        window_start="2026-04-13",
        window_end="2026-04-19",
        weeks=1,
        block="current",
    )

    assert result["sessions_analyzed"] == 1
    assert result["exercise_stats"]["Squat"]["max_kg"] == 100


def test_weekly_analysis_training_week_window_overrides_calendar_start() -> None:
    program = {
        "meta": {"program_start": "2026-04-01"},
        "phases": [{"name": "Build", "intent": "", "start_week": 1, "end_week": 8}],
        "sessions": [],
    }
    sessions = [
        make_session(6, [make_exercise("Squat", 140, 3, sets=4)], week_number=4),
        make_session(1, [make_exercise("Bench Press", 100, 3, sets=4)], week_number=4),
        make_session(0, [make_exercise("Deadlift", 180, 1, sets=3)], week_number=5, completed=False, status="planned"),
    ]

    result = analytics.weekly_analysis(
        program,
        sessions,
        window_start="2026-04-20",
        window_end="2026-04-24",
        week_start=4,
        week_end=4,
        weeks=1,
        block="current",
    )

    assert result["selected_week_start"] == 4
    assert result["selected_week_end"] == 4
    assert result["sessions_analyzed"] == 2
    assert result["exercise_stats"]["Squat"]["total_sets"] == 4
    assert result["exercise_stats"]["Squat"]["max_kg"] == 140
    assert result["compliance"]["planned"] == 2
    assert result["compliance"]["completed"] == 2


def test_weekly_analysis_uses_stored_saturday_week_start_for_current_block() -> None:
    program = {
        "meta": {
            "program_start": "2026-04-01",
            "block_week_start_days": {"current": "Saturday"},
        },
        "phases": [{"name": "Build", "intent": "", "start_week": 1, "end_week": 8}],
        "sessions": [],
    }
    sessions = [
        {"date": "2026-04-24", "week_number": 4, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Squat", 140, 1)]},
        {"date": "2026-04-25", "week_number": 5, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Bench Press", 100, 1)]},
    ]

    result = analytics.weekly_analysis(
        program,
        sessions,
        ref_date="2026-04-25",
        weeks=1,
        block="current",
    )

    assert result["week"] == 5
    assert result["selected_week_start"] == 5
    assert result["sessions_analyzed"] == 1
    assert "Bench Press" in result["exercise_stats"]
    assert "Squat" not in result["exercise_stats"]


def test_weekly_analysis_ref_date_drives_current_week_instead_of_today() -> None:
    program = {
        "meta": {"program_start": "2026-04-01"},
        "phases": [],
        "sessions": [],
    }
    sessions = [
        {"date": "2026-04-17", "week_number": 3, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Squat", 100, 1)]},
        {"date": "2026-04-24", "week_number": 4, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Squat", 120, 1)]},
    ]

    result = analytics.weekly_analysis(
        program,
        sessions,
        ref_date="2026-04-17",
        weeks=1,
        block="current",
    )

    assert result["week"] == 3
    assert result["selected_week_start"] == 3
    assert result["sessions_analyzed"] == 1
    assert result["exercise_stats"]["Squat"]["max_kg"] == 100


def test_weekly_analysis_week_gaps_count_positionally() -> None:
    program = {
        "meta": {"program_start": "2026-04-01"},
        "phases": [],
        "sessions": [],
    }
    sessions = [
        {"date": "2026-04-08", "week_number": 2, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Squat", 100, 1)]},
        {"date": "2026-04-29", "week_number": 5, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Squat", 120, 1)]},
    ]

    result = analytics.weekly_analysis(
        program,
        sessions,
        ref_date="2026-05-03",
        week_start=2,
        week_end=5,
        weeks=4,
        block="current",
    )

    assert result["selected_week_start"] == 2
    assert result["selected_week_end"] == 5
    assert result["selected_week_count"] == 4
    assert result["sessions_analyzed"] == 2


def test_weekly_analysis_saturday_current_week_uses_week_13_after_skipped_week_12() -> None:
    program = {
        "meta": {
            "program_start": "2026-02-15",
            "block_week_start_days": {"current": "Saturday"},
        },
        "phases": [],
        "sessions": [],
    }
    sessions = [
        {
            "date": "2026-05-05",
            "week_number": 12,
            "block": "current",
            "completed": False,
            "status": "planned",
            "exercises": [],
            "planned_exercises": [make_exercise("Squat", 100, 1)],
        },
        {
            "date": "2026-05-06",
            "week_number": 12,
            "block": "current",
            "completed": False,
            "status": "planned",
            "exercises": [],
            "planned_exercises": [make_exercise("Bench Press", 80, 1)],
        },
        {
            "date": "2026-05-09",
            "week_number": 13,
            "block": "current",
            "completed": True,
            "status": "completed",
            "exercises": [make_exercise("Deadlift", 220, 1)],
        },
        {
            "date": "2026-05-10",
            "week_number": 13,
            "block": "current",
            "completed": True,
            "status": "completed",
            "session_notes": "Logged after a timezone boundary.",
            "exercises": [make_exercise("Bench Press", 125, 1)],
        },
        {
            "date": "2026-05-12",
            "week_number": 13,
            "block": "current",
            "completed": False,
            "status": "planned",
            "session_notes": "Keep this paused deadlift variation in the analysis context.",
            "exercises": [],
            "planned_exercises": [make_exercise("Paused Deadlift", 180, 3, notes="Watch lockout position.")],
        },
    ]

    result = analytics.weekly_analysis(
        program,
        sessions,
        window_start="2026-05-09",
        window_end="2026-05-15",
        ref_date="2026-05-09",
        week_start=13,
        week_end=13,
        weeks=1,
        block="current",
    )

    assert result["week"] == 13
    assert result["selected_week_start"] == 13
    assert result["selected_week_end"] == 13
    assert result["sessions_analyzed"] == 2
    assert result["compliance"]["planned"] == 3
    assert result["compliance"]["completed"] == 2
    assert "Deadlift" in result["exercise_stats"]
    assert "Bench Press" in result["exercise_stats"]
    assert "Squat" not in result["exercise_stats"]
    assert any(
        session["date"] == "2026-05-12"
        and "paused deadlift" in session["session_notes"].lower()
        for session in result["selected_session_context"]
    )


def test_weekly_analysis_empty_current_week_keeps_history_current_state() -> None:
    program = {
        "meta": {
            "program_start": "2026-04-01",
            "block_week_start_days": {"current": "Saturday"},
        },
        "phases": [],
        "sessions": [],
    }
    sessions = []
    for idx, lift in enumerate(("Squat", "Bench Press", "Squat", "Bench Press", "Squat", "Bench Press")):
        sessions.append({
            "date": f"2026-04-{18 + idx:02d}",
            "week_number": 4,
            "block": "current",
            "completed": True,
            "status": "completed",
            "exercises": [make_exercise(lift, 100 + idx, 1)],
        })

    result = analytics.weekly_analysis(
        program,
        sessions,
        ref_date="2026-04-25",
        weeks=1,
        block="current",
    )

    assert result["week"] == 5
    assert result["sessions_analyzed"] == 0
    assert result["current_maxes"]["method"] == "session_estimated"
    assert result["current_maxes"]["squat"] > 0
    assert result["current_maxes"]["bench"] > 0


def test_weekly_analysis_infers_skipped_compliance_without_mutating_sessions() -> None:
    planned = {
        "date": "2026-04-08",
        "week_number": 2,
        "block": "current",
        "completed": False,
        "status": "planned",
        "exercises": [],
        "planned_exercises": [make_exercise("Squat", 100, 1)],
    }
    sessions = [
        planned,
        {"date": "2026-04-15", "week_number": 3, "block": "current", "completed": True, "status": "completed", "exercises": [make_exercise("Squat", 120, 1)]},
    ]
    program = {"meta": {"program_start": "2026-04-01"}, "phases": [], "sessions": []}

    result = analytics.weekly_analysis(
        program,
        sessions,
        ref_date="2026-04-15",
        week_start=2,
        week_end=3,
        weeks=2,
        block="current",
    )

    assert result["compliance"]["planned"] == 2
    assert result["compliance"]["completed"] == 1
    assert result["compliance"]["missed"] == 1
    assert planned["status"] == "planned"
    assert "_inferred_skipped" not in planned


def test_template_concretize_accepts_all_week_start_days() -> None:
    template = {
        "sessions": [
            {
                "id": "tpl-1",
                "week_number": 1,
                "day_of_week": "Monday",
                "day_index": 1,
                "label": "W1",
                "exercises": [
                    {"name": "Squat", "sets": 3, "reps": 5, "load_type": "absolute", "load_value": 100}
                ],
            }
        ]
    }

    for week_start_day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        sessions = template_apply.concretize(template, {}, [], date(2026, 4, 1), week_start_day)
        assert isinstance(sessions, list)


def test_template_concretize_shifted_week_one_drops_pre_program_start_sessions() -> None:
    template = {
        "sessions": [
            {"id": "sat", "week_number": 1, "day_of_week": "Saturday", "day_index": 6, "label": "W1", "exercises": []},
            {"id": "sun", "week_number": 1, "day_of_week": "Sunday", "day_index": 7, "label": "W1", "exercises": []},
            {"id": "wed", "week_number": 1, "day_of_week": "Wednesday", "day_index": 3, "label": "W1", "exercises": []},
        ]
    }

    sessions = template_apply.concretize(template, {}, [], date(2026, 4, 1), "Saturday")

    assert [session["date"] for session in sessions] == ["2026-04-01"]
    assert sessions[0]["day"] == "Wednesday"


def test_compute_banister_ffm_constant_load_stays_balanced() -> None:
    sessions = [
        make_sbd_session(
            days_ago,
            100,
            80,
            120,
            session_rpe=7,
            week_number=days_ago // 7 + 1,
        )
        for days_ago in range(19, -1, -1)
    ]

    result = analytics.compute_banister_ffm(
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=(TODAY - timedelta(days=19)).isoformat(),
        current_maxes={"squat": 200, "bench": 160, "deadlift": 240},
        ref_date=TODAY,
    )

    assert result["tsb_today"] == pytest.approx(0.0, abs=1e-6)
    assert result["tsb_label"] == "Building"
    assert len(result["series"]) == 20
    assert result["series"][0]["ctl"] == pytest.approx(result["series"][-1]["ctl"], abs=1e-6)
    assert result["series"][0]["atl"] == pytest.approx(result["series"][-1]["atl"], abs=1e-6)


def test_compute_monotony_strain_flags_high_monotony_and_strain_spike() -> None:
    sessions = []
    for week_idx in range(5):
        kg = 100 if week_idx < 4 else 200
        for day_offset in range(7):
            days_ago = 34 - (week_idx * 7 + day_offset)
            sessions.append(
                make_session(
                    days_ago,
                    [make_exercise("Squat", kg, 1)],
                    session_rpe=7,
                    week_number=week_idx + 1,
                )
            )

    result = analytics.compute_monotony_strain(
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=(TODAY - timedelta(days=34)).isoformat(),
        current_maxes={"squat": 200},
        ref_date=TODAY,
    )

    assert len(result["weekly"]) >= 5
    assert result["weekly"][0]["monotony"] > 2.0
    assert "high_monotony" in result["weekly"][0]["flags"]
    assert "strain_spike" in result["weekly"][-1]["flags"]


def test_compute_decoupling_flags_fatigue_dominant_streak() -> None:
    sessions = []
    week_payloads = [
        (100, 80, 120, 6),
        (102.5, 82.5, 122.5, 6),
        (105, 85, 125, 6),
        (100, 80, 120, 10),
        (95, 75, 115, 10),
        (90, 70, 110, 10),
    ]

    for week_idx, (squat, bench, deadlift, rpe) in enumerate(week_payloads):
        base_day = 41 - week_idx * 7
        sessions.append(
            make_sbd_session(
                base_day,
                squat,
                bench,
                deadlift,
                session_rpe=rpe,
                week_number=week_idx + 1,
            )
        )
        sessions.append(
            make_sbd_session(
                base_day - 2,
                squat,
                bench,
                deadlift,
                session_rpe=rpe,
                week_number=week_idx + 1,
            )
        )

    result = analytics.compute_decoupling(
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=(TODAY - timedelta(days=41)).isoformat(),
        current_maxes={"squat": 200, "bench": 160, "deadlift": 240},
        ref_date=TODAY,
    )

    assert result["current"] is not None
    assert result["current"]["decoupling"] < 0
    assert "decoupling_fatigue_dominant" in result["flags"]
    assert len(result["series"]) >= 3


def test_compute_taper_quality_gates_and_scores_inside_window() -> None:
    sessions = []
    program_start = (TODAY - timedelta(days=55)).isoformat()
    comp_date = (TODAY + timedelta(days=14)).isoformat()

    for week_idx in range(8):
        days_from_start = week_idx * 7
        if week_idx < 4:
            payloads = [
                (180, 135, 225, 9),
                (175, 132.5, 220, 9),
            ]
        else:
            payloads = [
                (170, 127.5, 212.5, 7),
            ]
        for offset, (squat, bench, deadlift, rpe) in enumerate(payloads):
            days_ago = 55 - days_from_start - (offset * 2)
            sessions.append(
                make_sbd_session(
                    days_ago,
                    squat,
                    bench,
                    deadlift,
                    session_rpe=rpe,
                    week_number=week_idx + 1,
                )
            )

    program = {
        "meta": {
            "program_start": program_start,
        },
        "phases": [
            {
                "name": "Taper",
                "intent": "taper and sharpen",
                "start_week": 5,
                "end_week": 8,
            }
        ],
        "competitions": [
            {
                "name": "Meet",
                "date": comp_date,
                "status": "confirmed",
                "weight_class_kg": 93,
            }
        ],
    }

    too_far_program = {
        **program,
        "competitions": [
            {
                "name": "Meet",
                "date": (TODAY + timedelta(days=28)).isoformat(),
                "status": "confirmed",
                "weight_class_kg": 93,
            }
        ],
    }

    gated = analytics.compute_taper_quality(
        too_far_program,
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=program_start,
        current_maxes={"squat": 200, "bench": 160, "deadlift": 240},
        ref_date=TODAY,
    )
    assert gated is None

    result = analytics.compute_taper_quality(
        program,
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        program_start=program_start,
        current_maxes={"squat": 200, "bench": 160, "deadlift": 240},
        ref_date=TODAY,
    )

    assert result["weeks_to_comp"] == pytest.approx(2.0, abs=1e-6)
    assert result["score"] >= 60
    assert result["label"] in {"good", "excellent"}
    assert set(result["components"].keys()) == {"volume_reduction", "intensity_maintained", "fatigue_trend", "tsb"}


def test_weekly_analysis_includes_peaking_layer_payloads() -> None:
    sessions = []
    for week_idx in range(8):
        base_day = 55 - (week_idx * 7)
        if week_idx < 4:
            payloads = [
                (180, 135, 225, 9),
                (175, 132.5, 220, 9),
            ]
        else:
            payloads = [
                (170, 127.5, 212.5, 7),
            ]
        for offset, (squat, bench, deadlift, rpe) in enumerate(payloads):
            sessions.append(
                make_sbd_session(
                    base_day - (offset * 2),
                    squat,
                    bench,
                    deadlift,
                    session_rpe=rpe,
                    week_number=week_idx + 1,
                )
            )

    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=55)).isoformat(),
        },
        "phases": [
            {
                "name": "Taper",
                "intent": "taper and sharpen",
                "start_week": 5,
                "end_week": 8,
            }
        ],
        "competitions": [
            {
                "name": "Meet",
                "date": (TODAY + timedelta(days=14)).isoformat(),
                "status": "confirmed",
                "weight_class_kg": 93,
            }
        ],
    }
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        }
    ]

    result = analytics.weekly_analysis(program, sessions, weeks=8, block="current", glossary=glossary)

    assert "banister" in result
    assert result["banister"] is not None
    assert result["banister"]["tsb_label"]
    assert "series" in result["banister"]
    assert "monotony_strain" in result
    assert len(result["monotony_strain"]["weekly"]) > 0
    assert "decoupling" in result
    assert result["decoupling"] is not None
    assert result["decoupling"]["current"] is not None
    assert "taper_quality" in result
    assert result["taper_quality"] is not None
    assert result["taper_quality"]["score"] >= 60


def test_weekly_analysis_includes_projection_calibration_and_landmarks() -> None:
    sessions = [
        make_sbd_session(
            77 - (idx * 7),
            100 + (idx * 5),
            80 + (idx * 4),
            120 + (idx * 6),
            session_rpe=10,
            week_number=idx + 1,
        )
        for idx in range(12)
    ]
    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=77)).isoformat(),
            "current_body_weight_kg": 90,
            "sex": "male",
        },
        "phases": [],
        "competitions": [
            {
                "name": "Older Meet",
                "date": (TODAY - timedelta(days=70)).isoformat(),
                "status": "completed",
                "results": {
                    "squat_kg": 98,
                    "bench_kg": 78,
                    "deadlift_kg": 118,
                    "total_kg": 294,
                    "prr": {"total": 1.04},
                },
            },
            {
                "name": "Recent Meet",
                "date": (TODAY - timedelta(days=28)).isoformat(),
                "status": "completed",
                "results": {
                    "squat_kg": 100,
                    "bench_kg": 80,
                    "deadlift_kg": 120,
                    "total_kg": 300,
                    "prr": {"total": 0.90},
                },
            },
            {
                "name": "Future Meet",
                "date": (TODAY + timedelta(days=14)).isoformat(),
                "status": "confirmed",
                "weight_class_kg": 93,
            },
        ],
    }
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Bench Press",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Deadlift",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
    ]

    result = analytics.weekly_analysis(program, sessions, weeks=12, block="current", glossary=glossary)

    assert result["projection_calibration"]["calibrated"] is True
    assert result["projection_calibration"]["meets"] == 2
    assert result["volume_landmarks"]["squat"]["confidence"] == "low"
    assert result["volume_landmarks"]["bench"]["confidence"] == "low"
    assert result["specificity_ratio"]["expected_band"] is not None
    assert result["specificity_ratio"]["narrow_status"] in {"below_expected", "within_expected", "above_expected"}


def test_generate_alerts_returns_deterministic_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analytics, "fatigue_index", lambda *args, **kwargs: {"score": 0.50})
    monkeypatch.setattr(analytics, "compute_readiness_score", lambda *args, **kwargs: {"score": 40.0})

    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=28)).isoformat(),
        },
        "phases": [
            {
                "name": "Base",
                "intent": "build",
                "start_week": 1,
                "end_week": 8,
                "target_rpe_max": 8,
            }
        ],
        "competitions": [
            {
                "name": "Meet A",
                "date": (TODAY + timedelta(days=21)).isoformat(),
                "status": "confirmed",
                "qualifying_total_kg": 550,
            }
        ],
    }
    sessions = [
        make_sbd_session(7, 140, 110, 170, session_rpe=8, week_number=4),
    ]
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        }
    ]
    analysis = {
        "week": 8,
        "fatigue_index": 0.75,
        "current_maxes": {"squat": 200, "bench": 160, "deadlift": 240},
        "projections": [
            {
                "total": 560,
                "confidence": 0.82,
                "weeks_to_comp": 3,
                "comp_name": "Meet A",
            }
        ],
        "banister": {
            "tsb_today": -35.0,
        },
        "acwr": {
            "composite": 1.82,
            "composite_zone": "load_spike",
        },
        "decoupling": {
            "flags": ["decoupling_fatigue_dominant"],
            "series": [
                {
                    "decoupling": -3.2,
                    "e1rm_slope_pct_per_week": -0.1,
                    "fi_slope_pct_points_per_week": 1.8,
                }
            ],
        },
        "specificity_ratio": {
            "narrow": 0.25,
            "expected_band": {
                "weeks_to_comp": 6.0,
                "narrow": {"min": 0.50, "max": 0.65},
                "broad": {"min": 0.75, "max": 0.85},
            },
            "flags": ["specificity_below_expected"],
        },
        "monotony_strain": {
            "weekly": [
                {
                    "week_start": (TODAY - timedelta(days=7)).isoformat(),
                    "monotony": 2.4,
                    "strain": 1450.0,
                    "flags": ["high_monotony"],
                }
            ]
        },
        "readiness_score": {
            "score": 42.0,
            "zone": "red",
            "components": {},
        },
    }

    alerts = analytics.generate_alerts(
        analysis,
        program,
        sessions,
        glossary,
        ref_date=TODAY,
        window_weeks=4,
    )

    assert [alert["source"] for alert in alerts] == [
        "fatigue",
        "acwr",
        "decoupling",
        "banister",
        "readiness",
        "specificity",
        "monotony",
        "projection",
    ]
    assert alerts[0]["severity"] == "warning"
    assert "fatigue_index=" in alerts[0]["raw_detail"]
    assert alerts[1]["message"] == "Training load jumped sharply. Monitor recovery closely."
    assert alerts[3]["message"] == "You are in deep overload. Performance should rebound after a deload."
    assert alerts[-1]["message"] == "You're projected to exceed the qualifying total for this meet."


def test_generate_alerts_uses_goal_owned_qualifying_total_when_competition_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analytics, "fatigue_index", lambda *args, **kwargs: {"score": 0.20})
    monkeypatch.setattr(analytics, "compute_readiness_score", lambda *args, **kwargs: {"score": 60.0})

    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=28)).isoformat(),
        },
        "goals": [
            {
                "id": "goal-1",
                "title": "Qualify",
                "goal_type": "qualify_for_federation",
                "priority": "primary",
                "target_competition_date": (TODAY + timedelta(days=21)).isoformat(),
                "target_total_kg": 550,
            }
        ],
        "phases": [],
        "competitions": [
            {
                "name": "Meet A",
                "date": (TODAY + timedelta(days=21)).isoformat(),
                "status": "confirmed",
            }
        ],
    }
    sessions = [
        make_sbd_session(7, 140, 110, 170, session_rpe=8, week_number=4),
    ]
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        }
    ]
    analysis = {
        "week": 8,
        "fatigue_index": 0.20,
        "current_maxes": {"squat": 200, "bench": 160, "deadlift": 240},
        "projections": [
            {
                "total": 560,
                "confidence": 0.82,
                "weeks_to_comp": 3,
                "comp_name": "Meet A",
            }
        ],
        "readiness_score": {
            "score": 60.0,
            "zone": "yellow",
            "components": {},
        },
    }

    alerts = analytics.generate_alerts(
        analysis,
        program,
        sessions,
        glossary,
        ref_date=TODAY,
        window_weeks=4,
    )

    assert alerts[-1]["message"] == "You're projected to exceed the qualifying total for this meet."
    assert "qualifying_total=550.0" in alerts[-1]["raw_detail"]


def test_weekly_analysis_includes_alerts_and_peaking_timeline_projection() -> None:
    sessions = []
    for week_idx in range(4):
        days_ago = 28 - (week_idx * 7)
        sessions.append(
            make_sbd_session(
                days_ago,
                150 + (week_idx * 2),
                115 + week_idx,
                180 + (week_idx * 2),
                session_rpe=8,
                week_number=week_idx + 1,
            )
        )

    future_session_date = TODAY + timedelta(days=7)
    sessions.append(
        {
            "date": future_session_date.isoformat(),
            "week_number": 5,
            "completed": False,
            "status": "planned",
            "planned_exercises": [
                make_exercise("Squat", 170, 3, sets=4),
                make_exercise("Bench Press", 125, 3, sets=4),
                make_exercise("Deadlift", 200, 2, sets=3),
            ],
            "exercises": [],
        }
    )

    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=28)).isoformat(),
        },
        "phases": [],
        "competitions": [
            {
                "name": "Spring Meet",
                "date": (TODAY + timedelta(days=14)).isoformat(),
                "status": "confirmed",
                "qualifying_total_kg": 100,
            }
        ],
    }
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Bench Press",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Deadlift",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
    ]

    with_future = analytics.weekly_analysis(program, sessions, weeks=8, block="current", glossary=glossary)
    baseline = analytics.weekly_analysis(
        program,
        [session for session in sessions if not session.get("planned_exercises")],
        weeks=8,
        block="current",
        glossary=glossary,
    )

    assert isinstance(with_future["alerts"], list)
    assert with_future["alerts"]
    assert with_future["alerts"][0]["source"] == "projection"

    peaking = with_future["peaking_timeline"]
    assert peaking["status"] in {"on_track", "misaligned", "significant_deviation"}
    assert peaking["comp_date"] == (TODAY + timedelta(days=14)).isoformat()
    assert peaking["series"][-1]["date"] == (TODAY + timedelta(days=28)).isoformat()
    assert peaking["specificity_points"]
    assert peaking["specificity_bands"]
    assert "closest_peak_date" in peaking
    assert all(
        abs(point["projected_tsb"]) < 1_000
        for point in peaking["series"]
        if point.get("projected_tsb") is not None
    )

    future_point = next(point for point in peaking["series"] if point["date"] == future_session_date.isoformat())
    baseline_point = next(point for point in baseline["peaking_timeline"]["series"] if point["date"] == future_session_date.isoformat())
    assert future_point["projected_tsb"] < baseline_point["projected_tsb"]


def test_weekly_analysis_peaking_timeline_ignores_noncanonical_planned_exercises() -> None:
    sessions = [
        make_sbd_session(14, 150, 110, 180, session_rpe=8, week_number=1),
        make_sbd_session(7, 152.5, 112.5, 182.5, session_rpe=8, week_number=2),
        {
            "date": (TODAY + timedelta(days=3)).isoformat(),
            "week_number": 3,
            "completed": False,
            "status": "planned",
            "planned_exercises": [
                make_exercise("Leg Press", 300, 10, sets=3),
                make_exercise("Chest Supported Row", 80, 10, sets=3),
            ],
            "exercises": [],
        },
    ]
    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=14)).isoformat(),
        },
        "phases": [],
        "competitions": [
            {
                "name": "Meet",
                "date": (TODAY + timedelta(days=14)).isoformat(),
                "status": "confirmed",
            }
        ],
    }
    glossary = [
        {
            "name": "Squat",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Bench Press",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Deadlift",
            "fatigue_profile": {
                "axial": 1.0,
                "neural": 1.0,
                "peripheral": 1.0,
                "systemic": 1.0,
            },
        },
        {
            "name": "Leg Press",
            "fatigue_profile": {
                "axial": 0.8,
                "neural": 0.2,
                "peripheral": 0.8,
                "systemic": 0.3,
            },
        },
        {
            "name": "Chest Supported Row",
            "fatigue_profile": {
                "axial": 0.2,
                "neural": 0.1,
                "peripheral": 0.5,
                "systemic": 0.2,
            },
        },
    ]

    result = analytics.weekly_analysis(program, sessions, weeks=4, block="current", glossary=glossary)

    assert result["peaking_timeline"]["comp_date"] == (TODAY + timedelta(days=14)).isoformat()
    assert result["peaking_timeline"]["series"]


def test_compute_prr_uses_snapshot_and_skips_invalid_lifts() -> None:
    partial_results = {
        "squat_kg": 210,
        "bench_kg": 0,
        "deadlift_kg": 250,
        "total_kg": 460,
    }
    partial_snapshot = {
        "squat_kg": 200,
        "bench_kg": 180,
        "deadlift_kg": 240,
        "total_kg": 620,
    }
    partial = analytics.compute_prr(partial_results, partial_snapshot)

    assert partial["squat"] == pytest.approx(1.05, abs=1e-6)
    assert partial["bench"] is None
    assert partial["deadlift"] == pytest.approx(1.042, abs=1e-3)
    assert partial["total"] is None

    full_results = {
        "squat_kg": 210,
        "bench_kg": 165,
        "deadlift_kg": 250,
        "total_kg": 625,
    }
    full_snapshot = {
        "squat_kg": 200,
        "bench_kg": 160,
        "deadlift_kg": 240,
        "total_kg": 600,
    }
    full = analytics.compute_prr(full_results, full_snapshot)

    assert full["squat"] == pytest.approx(1.05, abs=1e-6)
    assert full["bench"] == pytest.approx(1.031, abs=1e-3)
    assert full["deadlift"] == pytest.approx(1.042, abs=1e-3)
    assert full["total"] == pytest.approx(1.042, abs=1e-3)


def test_meet_projection_uses_calibrated_lambda_and_20_percent_ceiling() -> None:
    sessions = [
        make_sbd_session(21, 100, 80, 120, session_rpe=10, week_number=1),
        make_sbd_session(14, 110, 85, 130, session_rpe=10, week_number=2),
        make_sbd_session(7, 120, 90, 140, session_rpe=10, week_number=3),
    ]
    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=21)).isoformat(),
            "current_body_weight_kg": 90,
            "sex": "male",
        },
        "sessions": sessions,
        "competitions": [
            {
                "name": "Older Meet",
                "date": (TODAY - timedelta(days=70)).isoformat(),
                "status": "completed",
                "results": {
                    "squat_kg": 98,
                    "bench_kg": 78,
                    "deadlift_kg": 118,
                    "total_kg": 294,
                    "prr": {"total": 1.04},
                },
            },
            {
                "name": "Recent Meet",
                "date": (TODAY - timedelta(days=28)).isoformat(),
                "status": "completed",
                "results": {
                    "squat_kg": 100,
                    "bench_kg": 80,
                    "deadlift_kg": 120,
                    "total_kg": 300,
                    "prr": {"total": 0.90},
                },
            },
        ],
    }
    future_comp = (TODAY + timedelta(weeks=40)).isoformat()

    result = analytics.meet_projection(program, sessions, comp_date=future_comp, ref_date=TODAY)

    assert result["projection_calibration"]["calibrated"] is True
    assert result["projection_calibration"]["meets"] == 2
    assert result["projection_calibration"]["median_prr"] == pytest.approx(0.97, abs=1e-3)
    assert result["projection_calibration"]["lambda_multiplier"] == pytest.approx(0.97, abs=1e-3)
    assert result["lifts"]["squat"]["ceiling_clamped"] is True
    assert result["squat"] <= 120.0
    assert result["total"] <= 360.0


@pytest.mark.parametrize(
    ("weeks", "expected_confidence", "expects_data"),
    [
        (11, None, False),
        (12, "low", True),
        (18, "medium", True),
        (26, "high", True),
    ],
)
def test_compute_volume_landmarks_confidence_thresholds(
    weeks: int,
    expected_confidence: str | None,
    expects_data: bool,
) -> None:
    sessions = make_volume_landmark_sessions(weeks)
    program_start = (TODAY - timedelta(days=((weeks - 1) * 7) + 2)).isoformat()
    result = analytics.compute_volume_landmarks(
        sessions,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        current_maxes={"squat": 200},
        program_start=program_start,
        ref_date=TODAY,
    )

    squat = result["squat"]
    if not expects_data:
        assert squat["status"] == "insufficient_data"
        return

    assert squat["confidence"] == expected_confidence
    assert squat["mv"] is not None
    assert squat["mev"] is not None
    assert squat["mav"] is not None
    assert squat["mrv"] is not None


def test_compute_specificity_ratio_uses_expected_band_and_flags() -> None:
    sessions = [
        make_session(
            14 - (idx * 2),
            [make_exercise("Close Grip Bench", 100, 5, sets=10)],
            week_number=idx + 1,
        )
        for idx in range(5)
    ]
    glossary = [
        {
            "name": "Close Grip Bench",
            "category": "bench",
        }
    ]

    result = analytics.compute_specificity_ratio(sessions, glossary, weeks_to_comp=10)

    assert result["narrow"] == pytest.approx(0.0, abs=1e-6)
    assert result["broad"] == pytest.approx(1.0, abs=1e-6)
    assert result["secondary_sets"] == 50
    assert result["expected_band"]["weeks_to_comp"] == pytest.approx(10.0, abs=1e-6)
    assert result["expected_band"]["narrow"] == {"min": 0.5, "max": 0.65}
    assert result["expected_band"]["broad"] == {"min": 0.75, "max": 0.85}
    assert result["narrow_status"] == "below_expected"
    assert result["broad_status"] == "above_expected"
    assert "specificity_below_expected" in result["flags"]


def test_health_snapshot_and_completion_backfill_use_versioned_program(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot_program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=21)).isoformat(),
            "current_body_weight_kg": 90,
            "sex": "male",
        },
        "sessions": [],
        "competitions": [
            {
                "name": "Future Meet",
                "date": (TODAY + timedelta(days=7)).isoformat(),
                "status": "confirmed",
                "weight_class_kg": 93,
            }
        ],
    }
    snapshot_saved: dict[str, object] = {}

    def fake_snapshot_load(version: str, pk: str | None = None):
        assert version == "v002"
        return copy.deepcopy(snapshot_program), "program#v002", None

    def fake_snapshot_save(program: dict, sk: str, pk: str | None = None):
        snapshot_saved["program"] = copy.deepcopy(program)
        snapshot_saved["sk"] = sk
        snapshot_saved["pk"] = pk

    monkeypatch.setattr(core, "_load_program_version", fake_snapshot_load)
    monkeypatch.setattr(core, "_save_program_version", fake_snapshot_save)
    monkeypatch.setattr(
        analytics,
        "meet_projection",
        lambda *args, **kwargs: {"squat": 180, "bench": 120, "deadlift": 200, "total": 500},
    )

    snapshot_result = asyncio.run(core.health_snapshot_competition_projection(TODAY.isoformat(), version="v002"))
    assert snapshot_result["updated"] == 1
    assert snapshot_saved["sk"] == "program#v002"
    snapshot_comp = snapshot_saved["program"]["competitions"][0]
    assert snapshot_comp["projected_at_t_minus_1w"] == {
        "squat_kg": 180,
        "bench_kg": 120,
        "deadlift_kg": 200,
        "total_kg": 500,
    }
    assert snapshot_comp["projection_snapshot_date"] == TODAY.isoformat()

    completion_program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=21)).isoformat(),
            "current_body_weight_kg": 90,
            "sex": "male",
        },
        "sessions": [],
        "competitions": [
            {
                "name": "Completed Meet",
                "date": TODAY.isoformat(),
                "status": "confirmed",
                "weight_class_kg": 93,
            }
        ],
    }
    completion_saved: dict[str, object] = {}

    def fake_completion_load(version: str, pk: str | None = None):
        assert version == "v003"
        return copy.deepcopy(completion_program), "program#v003", None

    def fake_completion_save(program: dict, sk: str, pk: str | None = None):
        completion_saved["program"] = copy.deepcopy(program)
        completion_saved["sk"] = sk
        completion_saved["pk"] = pk

    def fake_completion_snapshot(program: dict, snapshot_date, allow_retrospective: bool = False):
        comp = program["competitions"][0]
        comp["projected_at_t_minus_1w"] = {
            "squat_kg": 200,
            "bench_kg": 100,
            "deadlift_kg": 250,
            "total_kg": 550,
        }
        comp["projection_snapshot_date"] = snapshot_date.isoformat()
        return program, [comp]

    monkeypatch.setattr(core, "_load_program_version", fake_completion_load)
    monkeypatch.setattr(core, "_save_program_version", fake_completion_save)
    monkeypatch.setattr(core, "_snapshot_competitions_in_program", fake_completion_snapshot)

    updated_comp = asyncio.run(
        core.health_complete_competition(
            TODAY.isoformat(),
            {"squat_kg": 210, "bench_kg": 95, "deadlift_kg": 260, "total_kg": 565},
            90,
            version="v003",
            post_meet_report={
                "attempts": [
                    {"lift": "squat", "attempt_number": 1, "kg": 190, "result": "made", "miss_reasons": [], "miss_category": None},
                    {"lift": "squat", "attempt_number": 2, "kg": 210, "result": "made", "miss_reasons": [], "miss_category": None},
                    {"lift": "squat", "attempt_number": 3, "kg": 220, "result": "missed", "miss_reasons": ["depth"], "miss_category": "judged_technical"},
                ],
                "sleep_hours": 6.5,
                "travel_notes": "two-hour drive",
                "warmup_timing": "squat warmups rushed",
                "pre_meet_food": "bagel",
                "during_meet_food": "rice bars",
                "caffeine_mg": 500,
                "caffeine_timing": "200mg before squat, 300mg before deadlift",
                "equipment_issues": "loose wrist wrap",
                "commands_missed": "soft squat rack command",
                "attempt_selection_grade": 4,
                "notes": "good execution overall",
            },
        )
    )

    assert updated_comp["status"] == "completed"
    assert updated_comp["projected_at_t_minus_1w"]["total_kg"] == 550
    assert updated_comp["results"]["prr"]["squat"] == pytest.approx(1.05, abs=1e-6)
    assert updated_comp["results"]["prr"]["bench"] == pytest.approx(0.95, abs=1e-6)
    assert updated_comp["results"]["prr"]["deadlift"] == pytest.approx(1.04, abs=1e-2)
    assert updated_comp["results"]["prr"]["total"] == pytest.approx(1.027, abs=1e-3)
    assert updated_comp["post_meet_report"]["sleep_hours"] == pytest.approx(6.5)
    assert updated_comp["post_meet_report"]["attempts"][2]["miss_reasons"] == ["depth"]
    assert completion_saved["sk"] == "program#v003"
    assert completion_saved["program"]["competitions"][0]["status"] == "completed"
    assert completion_saved["program"]["competitions"][0]["post_meet_report"]["attempt_selection_grade"] == 4


def test_readiness_wellness_penalty_and_fallback() -> None:
    sessions = [
        make_session(0, [], wellness=make_wellness(5, 5, 5, 5, 5)),
        make_session(3, [], wellness=make_wellness(1, 1, 1, 1, 1)),
    ]

    result = analytics._readiness_wellness_component(sessions, reference_date=TODAY)
    assert result["mean"] == pytest.approx(3.0, abs=1e-6)
    assert result["penalty"] == pytest.approx(0.4, abs=1e-6)

    fallback = analytics._readiness_wellness_component([make_session(0, [])], reference_date=TODAY)
    assert fallback["mean"] is None
    assert fallback["penalty"] == pytest.approx(0.5, abs=1e-6)


def test_readiness_performance_trend_penalizes_negative_slope_only() -> None:
    current_maxes = {"squat": 100, "bench": 100, "deadlift": 100}
    negative_sessions = [
        make_session(14, [make_exercise("Squat", 100, 1)], session_rpe=10, week_number=1),
        make_session(7, [make_exercise("Squat", 95, 1)], session_rpe=10, week_number=2),
        make_session(0, [make_exercise("Squat", 90, 1)], session_rpe=10, week_number=3),
    ]
    negative = analytics._readiness_performance_trend_component(
        negative_sessions,
        current_maxes=current_maxes,
        reference_date=TODAY,
    )
    assert negative["slope_kg_per_week"] == pytest.approx(-5.0, abs=1e-6)
    assert negative["penalty"] == pytest.approx(1.0, abs=1e-6)

    positive_sessions = [
        make_session(14, [make_exercise("Squat", 90, 1)], session_rpe=10, week_number=1),
        make_session(7, [make_exercise("Squat", 95, 1)], session_rpe=10, week_number=2),
        make_session(0, [make_exercise("Squat", 100, 1)], session_rpe=10, week_number=3),
    ]
    positive = analytics._readiness_performance_trend_component(
        positive_sessions,
        current_maxes=current_maxes,
        reference_date=TODAY,
    )
    assert positive["slope_kg_per_week"] == pytest.approx(5.0, abs=1e-6)
    assert positive["penalty"] == pytest.approx(0.0, abs=1e-6)


def test_readiness_bodyweight_component_is_cut_aware_and_falls_back_without_series() -> None:
    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=28)).isoformat(),
            "comp_date": (TODAY + timedelta(days=28)).isoformat(),
            "weight_class_kg": 86,
            "current_body_weight_kg": 90,
        },
        "competitions": [
            {
                "date": (TODAY + timedelta(days=28)).isoformat(),
                "status": "confirmed",
                "weight_class_kg": 86,
            }
        ],
    }
    cut_sessions = [
        make_session(14, [], body_weight_kg=92),
        make_session(7, [], body_weight_kg=91),
        make_session(0, [], body_weight_kg=90),
    ]

    cut_result = analytics._readiness_bodyweight_component(cut_sessions, program, reference_date=TODAY)
    assert cut_result["mode"] == "cut"
    assert cut_result["expected_weekly_change_kg"] == pytest.approx(-1.0, abs=1e-6)
    assert cut_result["actual_weekly_change_kg"] == pytest.approx(-1.0, abs=1e-6)
    assert cut_result["penalty"] == pytest.approx(0.0, abs=1e-6)

    fallback = analytics._readiness_bodyweight_component([make_session(0, [], body_weight_kg=None)], program, reference_date=TODAY)
    assert fallback["mode"] == "fallback"
    assert fallback["penalty"] == pytest.approx(0.5, abs=1e-6)


def test_compute_readiness_score_uses_new_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analytics, "fatigue_index", lambda *args, **kwargs: {"score": 0.2})
    monkeypatch.setattr(analytics, "_readiness_wellness_component", lambda *args, **kwargs: {"penalty": 0.4})
    monkeypatch.setattr(analytics, "_readiness_performance_trend_component", lambda *args, **kwargs: {"penalty": 0.3})
    monkeypatch.setattr(analytics, "_readiness_bodyweight_component", lambda *args, **kwargs: {"penalty": 0.1})

    program = {
        "meta": {
            "program_start": (TODAY - timedelta(days=14)).isoformat(),
            "weight_class_kg": 86,
            "current_body_weight_kg": 90,
        },
        "phases": [
            {
                "name": "Base",
                "intent": "build",
                "start_week": 1,
                "end_week": 12,
                "target_rpe_min": 7,
                "target_rpe_max": 9,
            }
        ],
    }
    sessions = [
        make_session(
            0,
            [make_exercise("Squat", 100, 1)],
            session_rpe=9,
            body_weight_kg=90,
            wellness=make_wellness(4, 4, 4, 4, 4),
            week_number=3,
        )
    ]

    result = analytics.compute_readiness_score(sessions, program, program_start=program["meta"]["program_start"])

    assert result["training_score"] == pytest.approx(68.5, abs=1e-6)
    assert result["external_score"] == pytest.approx(72.0, abs=1e-6)
    assert result["score"] == pytest.approx(69.5, abs=0.2)
    assert result["zone"] == "yellow"
    assert result["components"]["fatigue_norm"] == pytest.approx(0.2, abs=1e-6)
    assert result["components"]["rpe_drift"] == pytest.approx(0.5, abs=1e-6)
    assert result["components"]["wellness"] == pytest.approx(0.4, abs=1e-6)
    assert result["components"]["performance_trend"] == pytest.approx(0.3, abs=1e-6)
    assert result["components"]["bw_deviation"] == pytest.approx(0.1, abs=1e-6)
    assert "miss_rate" not in result["components"]
    assert "compliance_pct" not in result["components"]
    assert result["training_readiness_confidence"] == pytest.approx(1.0, abs=1e-6)
    assert result["external_readiness_confidence"] == pytest.approx(1.0, abs=1e-6)


def test_fatigue_index_uses_one_based_calendar_weeks() -> None:
    program_start = (TODAY - timedelta(days=28)).isoformat()
    sessions = [
        {
            "date": (TODAY - timedelta(days=28 - (week * 7))).isoformat(),
            "completed": True,
            "status": "completed",
            "exercises": [make_exercise("Squat", 100 + week, 3, sets=3)],
            "session_rpe": 7,
        }
        for week in range(4)
    ]

    result = analytics.fatigue_index(
        sessions,
        days=28,
        program_start=program_start,
        ref_date=TODAY,
        current_maxes={"squat": 200},
    )

    assert result["fatigue_model"] == "reservoir_v2"
    assert result["components"]["fatigue_window_weeks"] == 5
    assert result["components"]["current_state_fi"] == result["score"]


def test_fatigue_current_state_is_stable_across_filters() -> None:
    program_start_date = TODAY - timedelta(days=56)
    sessions = [
        make_session(
            56 - (week * 7),
            [make_exercise("Bench Press", 80 + week, 5, sets=4)],
            session_rpe=7 + (0.1 * week),
            week_number=week + 1,
        )
        for week in range(8)
    ]

    full = analytics.fatigue_index(
        sessions,
        days=56,
        program_start=program_start_date.isoformat(),
        ref_date=TODAY,
        current_maxes={"bench": 120},
    )
    one_week = analytics.fatigue_index(
        sessions,
        days=7,
        program_start=program_start_date.isoformat(),
        ref_date=TODAY,
        current_maxes={"bench": 120},
    )

    assert full["score"] == pytest.approx(one_week["score"], abs=1e-6)
    assert full["window_mean_fi"] != one_week["window_mean_fi"]


def test_smolov_style_bench_localized_reservoir_is_not_diluted() -> None:
    program_start = TODAY - timedelta(days=70)
    sessions = []
    for week in range(8):
        sessions.append(
            make_session(
                70 - (week * 7),
                [make_exercise("Bench Press", 70, 5, sets=5)],
                session_rpe=7,
                week_number=week + 1,
            )
        )
    for day in range(5):
        sessions.append(
            make_session(
                day,
                [make_exercise("Bench Press", 85, 5, sets=10)],
                session_rpe=9,
                week_number=11,
            )
        )
    glossary = [
        {
            "name": "Bench Press",
            "category": "bench",
            "fatigue_profile": {"axial": 0.1, "neural": 1.0, "peripheral": 1.0, "systemic": 0.4},
        }
    ]

    result = analytics.fatigue_index(
        sessions,
        days=7,
        glossary=glossary,
        program_start=program_start.isoformat(),
        ref_date=TODAY,
        current_maxes={"bench": 100},
    )

    dims = result["components"]["reservoir_dimension_stress"]
    assert max(dims.values()) >= 0.75
    assert "localized_fatigue_high" in result["flags"]


def test_inol_ramp_up_grace_and_later_low_stimulus_flag() -> None:
    program_start = (TODAY - timedelta(days=28)).isoformat()
    week1 = [make_session(28, [make_exercise("Squat", 100, 1, sets=1)], week_number=1)]
    week5 = [make_session(0, [make_exercise("Squat", 100, 1, sets=1)], week_number=5)]
    history = week1 + [
        make_session(21, [make_exercise("Squat", 150, 3, sets=4)], week_number=2),
        make_session(14, [make_exercise("Squat", 150, 3, sets=4)], week_number=3),
        make_session(7, [make_exercise("Squat", 150, 3, sets=4)], week_number=4),
    ] + week5

    early = analytics.compute_inol(
        week1,
        program_start=program_start,
        current_maxes={"squat": 200},
        phases=[],
        selected_weeks=1,
        all_history_sessions=history,
        ref_date=TODAY - timedelta(days=28),
    )
    later = analytics.compute_inol(
        week5,
        program_start=program_start,
        current_maxes={"squat": 200},
        phases=[],
        selected_weeks=1,
        all_history_sessions=history,
        ref_date=TODAY,
    )

    assert early["ramp_up_grace"]["squat"] is True
    assert "low_stimulus_squat" not in early["flags"]
    assert later["ramp_up_grace"]["squat"] is False
    assert "low_stimulus_squat" in later["flags"]


def test_inol_trend_pressure_strengthens_high_warning() -> None:
    program_start = (TODAY - timedelta(days=35)).isoformat()
    history = [
        make_session(35, [make_exercise("Bench Press", 70, 5, sets=3)], week_number=1),
        make_session(28, [make_exercise("Bench Press", 70, 5, sets=3)], week_number=2),
        make_session(21, [make_exercise("Bench Press", 70, 5, sets=3)], week_number=3),
        make_session(14, [make_exercise("Bench Press", 70, 5, sets=3)], week_number=4),
        make_session(0, [make_exercise("Bench Press", 90, 5, sets=14)], week_number=6),
    ]

    result = analytics.compute_inol(
        [history[-1]],
        program_start=program_start,
        current_maxes={"bench": 100},
        phases=[],
        selected_weeks=1,
        all_history_sessions=history,
        ref_date=TODAY,
    )

    assert result["trend_pressure"]["bench"]["value"] > 0.35
    assert "overreaching_risk_bench" in result["flags"]


def test_monotony_small_loads_are_capped_and_require_training_days() -> None:
    sessions = [
        make_session(0, [make_exercise("Squat", 20, 1, sets=1, failed=True)], session_rpe=10, week_number=1)
    ]

    result = analytics.compute_monotony_strain(
        sessions,
        program_start=TODAY.isoformat(),
        current_maxes={"squat": 200},
        ref_date=TODAY,
    )

    row = result["weekly"][-1]
    assert row["monotony"] <= 7.0
    assert row["strain"] < 1_000_000
    assert row["nonzero_training_days"] == 1
    assert "high_monotony" not in row["flags"]


def test_planned_load_resolver_and_unresolved_sets() -> None:
    current_maxes = {"squat": 200, "bench": 100}
    assert analytics._planned_exercise_weight({"name": "Squat", "kg": 120, "sets": 1, "reps": 1}, current_maxes) == pytest.approx(120)
    assert analytics._planned_exercise_weight({"name": "Squat", "percent": 0.8, "sets": 1, "reps": 1}, current_maxes) == pytest.approx(160)
    assert analytics._planned_exercise_weight({"name": "Bench Press", "rpe_target": 8, "sets": 1, "reps": 3}, current_maxes) == pytest.approx(87.5)
    assert analytics._planned_exercise_weight({"name": "Squat", "load_type": "unspecified", "sets": 1, "reps": 1}, current_maxes) is None

    future = [
        {
            "date": (TODAY + timedelta(days=1)).isoformat(),
            "status": "planned",
            "completed": False,
            "planned_exercises": [
                {"name": "Squat", "percent": 0.8, "sets": 3, "reps": 3},
                {"name": "Squat", "load_type": "unspecified", "sets": 2, "reps": 5},
            ],
        }
    ]
    daily, unresolved = analytics._future_planned_daily_fatigue(
        future,
        glossary=[{"name": "Squat", "fatigue_profile": {"axial": 1.0, "neural": 1.0, "peripheral": 1.0, "systemic": 1.0}}],
        current_maxes=current_maxes,
        ref_date=TODAY,
        end_day=TODAY + timedelta(days=7),
    )

    assert (TODAY + timedelta(days=1)) in daily
    assert unresolved == 2


def test_accessory_e1rm_estimate_is_used_for_intensity() -> None:
    intensity = analytics._resolve_intensity(
        "leg press",
        weight=200,
        reps=8,
        rpe=None,
        current_maxes={},
        glossary=[
            {
                "name": "Leg Press",
                "category": "machine",
                "e1rm_estimate": {"value_kg": 400},
            }
        ],
    )

    assert intensity == pytest.approx(0.5, abs=1e-6)


def test_specificity_target_prefers_primary_goal_meet() -> None:
    program = {
        "meta": {"program_name": "Block", "comp_date": (TODAY + timedelta(days=21)).isoformat()},
        "goals": [
            {
                "priority": "primary",
                "target_competition_dates": [(TODAY + timedelta(days=42)).isoformat()],
            }
        ],
        "competitions": [
            {"name": "Optional Tune Up", "date": (TODAY + timedelta(days=21)).isoformat(), "status": "optional"},
            {"name": "Primary Meet", "date": (TODAY + timedelta(days=42)).isoformat(), "status": "confirmed"},
        ],
    }

    selected = analytics._select_specificity_target_competition(program, TODAY)
    assert selected["name"] == "Primary Meet"
    assert selected["selection_reason"] == "primary_goal"

    fallback_program = {**program, "goals": []}
    selected_fallback = analytics._select_specificity_target_competition(fallback_program, TODAY)
    assert selected_fallback["name"] == "Optional Tune Up"
    assert selected_fallback["selection_reason"] == "nearest_confirmed"
