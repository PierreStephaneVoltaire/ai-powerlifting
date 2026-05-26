from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prompt_context  # noqa: E402


def test_summarize_goals_resolves_linked_standard_and_competition() -> None:
    program = {
        "goals": [
            {
                "id": "goal-1",
                "title": "Qualify at Provincials",
                "goal_type": "qualify_for_federation",
                "priority": "primary",
                "strategy_mode": "qualify",
                "risk_tolerance": "medium",
                "target_competition_dates": ["2026-06-20"],
                "target_standard_ids": ["std-1"],
                "acceptable_weight_classes_kg": [74, 83],
            }
        ],
        "competitions": [
            {
                "name": "Provincials",
                "date": "2026-06-20",
                "status": "confirmed",
                "federation": "OPA",
                "federation_id": "fed-2",
                "counts_toward_federation_ids": ["fed-1"],
                "weight_class_kg": 83,
            }
        ],
    }
    federation_library = {
        "federations": [
            {
                "id": "fed-1",
                "name": "CPU",
                "abbreviation": "CPU",
            },
            {
                "id": "fed-2",
                "name": "OPA",
                "abbreviation": "OPA",
            },
        ],
        "qualification_standards": [
            {
                "id": "std-1",
                "federation_id": "fed-1",
                "season_year": 2026,
                "sex": "male",
                "equipment": "raw",
                "event": "sbd",
                "weight_class_kg": 83,
                "required_total_kg": 570,
            }
        ],
    }

    result = prompt_context.summarize_goals(
        program,
        federation_library=federation_library,
        reference_date=date(2026, 4, 25),
    )

    assert result["competition_goal_priorities"] == {"2026-06-20": "primary"}
    goal = result["goals"][0]
    assert goal["target_total_kg"] == 570
    assert goal["target_weight_class_kg"] == 83
    assert goal["target_federation"]["name"] == "CPU"
    assert goal["linked_competition"]["name"] == "Provincials"
    assert goal["linked_competitions"][0]["matching_required_total_kg"] == 570
    assert goal["linked_competition"]["goal_federation_eligible"] is True
    assert goal["linked_competition"]["weight_class_alignment"] == "target"


def test_summarize_program_notes_keeps_chronological_evolving_context() -> None:
    program = {
        "meta": {
            "block_notes": [
                {
                    "date": "2026-04-10",
                    "notes": "Back fatigue resolved; return to normal pulling.",
                    "updated_at": "2026-04-10T08:00:00Z",
                },
                {
                    "date": "2026-04-03",
                    "notes": "Back fatigue elevated after travel.",
                    "updated_at": "2026-04-03T08:00:00Z",
                },
                {
                    "date": "2026-03-20",
                    "notes": "Older block context.",
                    "updated_at": "2026-03-20T08:00:00Z",
                },
            ]
        }
    }

    result = prompt_context.summarize_program_notes(program, window_start=date(2026, 4, 1))

    assert result["entries"] == 2
    assert [note["date"] for note in result["chronological_notes"]] == ["2026-04-03", "2026-04-10"]
    assert "conflict" in result["interpretation"]
    assert "newer dated notes" in result["interpretation"]


def test_summarize_competitions_uses_goal_priority_and_goal_owned_standard() -> None:
    program = {
        "meta": {
            "sex": "male",
            "current_body_weight_kg": 82.4,
        },
        "goals": [
            {
                "id": "goal-1",
                "title": "Main goal",
                "priority": "primary",
                "target_competition_dates": ["2026-07-18"],
                "strategy_mode": "qualify",
                "goal_type": "qualify_for_federation",
                "target_standard_ids": ["std-1"],
            }
        ],
        "competitions": [
            {
                "name": "Tune-up",
                "date": "2026-06-13",
                "status": "optional",
                "weight_class_kg": 83,
                "targets": {"total_kg": 550},
            },
            {
                "name": "Nationals",
                "date": "2026-07-18",
                "status": "confirmed",
                "federation": "OPA",
                "federation_id": "fed-2",
                "counts_toward_federation_ids": ["fed-1"],
                "weight_class_kg": 83,
                "targets": {"total_kg": 575},
            },
        ],
    }
    federation_library = {
        "federations": [
            {"id": "fed-1", "name": "CPU", "abbreviation": "CPU"},
            {"id": "fed-2", "name": "OPA", "abbreviation": "OPA"},
        ],
        "qualification_standards": [
            {
                "id": "std-1",
                "federation_id": "fed-1",
                "season_year": 2026,
                "sex": "male",
                "equipment": "raw",
                "event": "sbd",
                "weight_class_kg": 83,
                "required_total_kg": 570,
            }
        ],
    }

    goals = prompt_context.summarize_goals(program, federation_library=federation_library, reference_date=date(2026, 4, 25))
    result = prompt_context.summarize_competitions(
        program,
        reference_date=date(2026, 4, 25),
        federation_library=federation_library,
        competition_goal_priorities=goals["competition_goal_priorities"],
    )

    assert result["primary_competition"]["name"] == "Nationals"
    assert result["competitions"][1]["goal_priority"] == "primary"
    assert result["competitions"][1]["eligible_federation_ids"] == ["fed-2", "fed-1"]
    assert result["competitions"][1]["primary_strategy_mode"] == "qualify"
    assert result["competitions"][1]["linked_goals"][0]["linked_standard"]["required_total_kg"] == 570
    assert result["competitions"][1]["governing_goal"]["required_total_kg"] == 570
    assert result["competitions"][1]["linked_goals"][0]["goal_federation_eligible"] is True


def test_summarize_competitions_keeps_harder_primary_standard_when_goal_has_multiple_paths() -> None:
    program = {
        "meta": {
            "sex": "male",
            "current_body_weight_kg": 82.8,
        },
        "goals": [
            {
                "id": "goal-1",
                "title": "Qualify OPA or CPU",
                "priority": "primary",
                "goal_type": "qualify_for_federation",
                "strategy_mode": "qualify",
                "target_federation_id": "fed-2",
                "target_competition_dates": ["2026-06-14", "2026-07-12"],
                "target_standard_ids": ["std-opa", "std-cpu"],
            }
        ],
        "competitions": [
            {
                "name": "Sunny Daze",
                "date": "2026-06-14",
                "status": "confirmed",
                "federation": "OPA",
                "federation_id": "fed-2",
                "counts_toward_federation_ids": ["fed-1"],
                "weight_class_kg": 83,
                "notes": "Primary qualifying shot.",
            },
            {
                "name": "Horseshow Showdown",
                "date": "2026-07-12",
                "status": "confirmed",
                "federation": "OPA",
                "federation_id": "fed-2",
                "counts_toward_federation_ids": ["fed-1"],
                "weight_class_kg": 83,
                "notes": "Backup qualifying shot.",
            },
        ],
    }
    federation_library = {
        "federations": [
            {"id": "fed-1", "name": "CPU", "abbreviation": "CPU"},
            {"id": "fed-2", "name": "OPA", "abbreviation": "OPA"},
        ],
        "qualification_standards": [
            {
                "id": "std-cpu",
                "federation_id": "fed-1",
                "season_year": 2026,
                "sex": "male",
                "equipment": "raw",
                "event": "sbd",
                "weight_class_kg": 83,
                "required_total_kg": 535,
            },
            {
                "id": "std-opa",
                "federation_id": "fed-2",
                "season_year": 2026,
                "sex": "male",
                "equipment": "raw",
                "event": "sbd",
                "weight_class_kg": 83,
                "required_total_kg": 570,
            },
        ],
    }

    goals = prompt_context.summarize_goals(program, federation_library=federation_library, reference_date=date(2026, 4, 25))
    result = prompt_context.summarize_competitions(
        program,
        reference_date=date(2026, 4, 25),
        federation_library=federation_library,
        competition_goal_priorities=goals["competition_goal_priorities"],
    )

    assert goals["goals"][0]["remaining_eligible_opportunities"] == 2
    assert [item["date"] for item in goals["goals"][0]["linked_competitions"]] == ["2026-06-14", "2026-07-12"]
    assert result["competitions"][0]["governing_goal"]["required_total_kg"] == 570
    assert result["competitions"][0]["governing_goal"]["matching_required_total_kg"] == 570
    assert result["competitions"][0]["notes"] == "Primary qualifying shot."
    assert result["competitions"][1]["governing_goal"]["required_total_kg"] == 570


def test_summarize_meet_interference_flags_close_turnaround() -> None:
    program = {
        "goals": [
            {
                "id": "goal-0",
                "title": "Qualifier",
                "priority": "secondary",
                "strategy_mode": "qualify",
                "target_competition_date": "2026-06-14",
            },
            {
                "id": "goal-1",
                "title": "Primary meet",
                "priority": "primary",
                "target_competition_date": "2026-07-05",
                "strategy_mode": "max_total",
            }
        ],
        "competitions": [
            {
                "name": "Qualifier",
                "date": "2026-06-14",
                "status": "confirmed",
                "hotel_required": True,
                "weight_class_kg": 74,
            },
            {
                "name": "Primary Meet",
                "date": "2026-07-05",
                "status": "confirmed",
                "weight_class_kg": 83,
            },
        ],
    }

    result = prompt_context.summarize_meet_interference(
        program,
        reference_date=date(2026, 4, 25),
    )

    assert result
    assert result[0]["risk_level"] == "high"
    assert "travel or hotel load present" in result[0]["risk_flags"]
