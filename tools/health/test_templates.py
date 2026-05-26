from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402
import template_apply  # noqa: E402
from template_store import TemplateNotFoundError, TemplateStore  # noqa: E402


class FakeTemplateTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def get_item(self, Key: dict) -> dict:
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item is not None else {}

    def put_item(self, Item: dict) -> None:
        self.items[(Item["pk"], Item["sk"])] = Item


def make_store() -> TemplateStore:
    store = TemplateStore("fake", pk="template_library")
    store._table = FakeTemplateTable()
    return store


def minimal_template(name: str) -> dict:
    return {
        "meta": {"name": name, "estimated_weeks": 1, "days_per_week": 1},
        "sessions": [
            {
                "id": "day-1",
                "week_number": 1,
                "day_of_week": "Monday",
                "day_index": 1,
                "exercises": [],
            }
        ],
    }


def test_global_template_store_filters_unpublished_drafts_by_author() -> None:
    store = make_store()
    published_sk = store.put_template_sync(
        minimal_template("Published"),
        actor_pk="alice",
        author="Alice",
        published=True,
        sk="template#published",
    )
    draft_sk = store.put_template_sync(
        minimal_template("Draft"),
        actor_pk="alice",
        author="Alice",
        published=False,
        sk="template#draft",
    )

    assert [row["sk"] for row in store.list_templates_sync(actor_pk=None)] == [published_sk]
    assert {row["sk"] for row in store.list_templates_sync(actor_pk="alice")} == {published_sk, draft_sk}
    assert [row["sk"] for row in store.list_templates_sync(actor_pk="bob")] == [published_sk]
    assert store.get_template_sync(draft_sk, actor_pk="bob") is None

    with pytest.raises(TemplateNotFoundError):
        store.set_published_sync(draft_sk, True, actor_pk="bob")

    store.set_published_sync(draft_sk, True, actor_pk="alice")
    assert {row["sk"] for row in store.list_templates_sync(actor_pk=None)} == {published_sk, draft_sk}


def test_prepare_template_payload_normalizes_percentages_and_required_maxes() -> None:
    prepared = core._prepare_template_payload(
        {
            "meta": {"name": "Imported"},
            "sessions": [
                {
                    "week_number": "2",
                    "day_index": "3",
                    "exercises": [
                        {
                            "name": "Squat",
                            "glossary_id": "squat",
                            "sets": 3,
                            "reps": 5,
                            "load_type": "percentage",
                            "load_value": 75,
                        },
                        {
                            "name": "Bench",
                            "glossary_id": "bench",
                            "sets": 4,
                            "reps": 6,
                            "load_type": "rpe",
                            "rpe_target": 8,
                        },
                        {"name": "Unknown Curl", "load_type": "percentage", "load_value": "bad"},
                    ],
                }
            ],
        }
    )

    session = prepared["sessions"][0]
    assert session["week_number"] == 2
    assert session["day_of_week"] == "Wednesday"
    assert prepared["meta"]["estimated_weeks"] == 2
    assert prepared["meta"]["days_per_week"] == 1
    assert prepared["required_maxes"] == ["bench", "squat"]
    assert prepared["glossary_resolution"]["unresolved"] == ["Unknown Curl"]
    assert session["exercises"][0]["load_value"] == pytest.approx(0.75)
    assert session["exercises"][2]["load_type"] == "unresolvable"


def test_concretize_estimates_rpe_load_from_e1rm() -> None:
    template = {
        "sessions": [
            {
                "id": "day-1",
                "week_number": 1,
                "day_of_week": "Monday",
                "day_index": 1,
                "label": "W1D1",
                "exercises": [
                    {
                        "name": "Squat",
                        "glossary_id": "squat",
                        "sets": 1,
                        "reps": 5,
                        "load_type": "rpe",
                        "rpe_target": 8,
                    }
                ],
            }
        ]
    }

    sessions = template_apply.concretize(template, {"squat": 200}, [], date(2026, 5, 4), "Monday")

    exercise = sessions[0]["planned_exercises"][0]
    assert exercise["load_source"] == "rpe_estimate"
    assert exercise["kg"] == pytest.approx(162.5)
