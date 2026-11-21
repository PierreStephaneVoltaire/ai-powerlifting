import copy
import asyncio
import json

import pytest


from services.runtime.template_store import TemplateStore
from services.templates.template_apply_confirm.core import _new_sessions
from services.templates.template_apply.template_apply import check_max_resolution_gate, concretize
from services.templates.template_create_from_block.template_convert import convert_block_to_template


class PlainTable:
    def __init__(self):
        self.items = {}
        self.puts = 0

    def get_item(self, *, Key, **kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, *, Item, **kwargs):
        assert "ConditionExpression" not in kwargs
        self.items[(Item["pk"], Item["sk"])] = copy.deepcopy(Item)
        self.puts += 1


def store():
    result = TemplateStore("templates")
    result._table = PlainTable()
    return result


def template(name="Base", author="alice", published=False):
    return {"meta": {"name": name, "author_pk": author, "author": author, "published": published}, "phases": [], "sessions": []}


def seed(result, sk="template#1", item=None):
    item = item or template()
    item = {**copy.deepcopy(item), "pk": result.pk, "sk": sk}
    result.table.items[(result.pk, sk)] = item
    result._write_index_sync([result._summary(item)])


def test_publication_is_a_plain_write_of_template_and_index():
    result = store()
    seed(result)
    result.set_published_sync("template#1", True, actor_pk="alice")
    assert result.table.items[(result.pk, "template#1")]["meta"]["published"] is True
    assert [item["published"] for item in result.table.items[(result.pk, result.INDEX_SK)]["templates"]] == [True]


def test_creating_the_same_template_twice_makes_two_templates():
    result = store()
    first = result.put_template_sync(template("New"), actor_pk="alice", published=False)
    second = result.put_template_sync(template("New"), actor_pk="alice", published=False)
    assert first != second
    assert sorted(item["sk"] for item in result.list_templates_sync(actor_pk="alice")) == sorted([first, second])


@pytest.mark.parametrize("exercise", [
    {"duration_minutes": value} for value in (0, -5, "fifteen", float("nan"), True)
] + [{"duration_minutes": 15, "rep_mode": "amrap"}, {"rep_mode": "amrap", "reps": 8}, {"rep_mode": "unknown"}])
def test_invalid_prescriptions_do_not_create_or_overwrite_a_template(exercise):
    result = store()
    seed(result)
    incoming = {"sessions": [{"exercises": [exercise]}]}
    with pytest.raises(ValueError):
        result.put_template_sync(incoming, actor_pk="alice")
    with pytest.raises(ValueError):
        result.update_template_sync("template#1", incoming, actor_pk="alice")
    assert result.get_template_sync("template#1", actor_pk="alice")["sessions"] == []


def test_existing_cardio_duration_can_be_saved_from_a_legacy_client():
    result = store()
    seed(result)
    result.update_template_sync("template#1", {"sessions": [{"exercises": [{"duration_minutes": "15"}]}]}, actor_pk="alice")
    assert result.get_template_sync("template#1", actor_pk="alice")["sessions"][0]["exercises"][0]["duration_minutes"] == 15


def test_index_keeps_templates_created_by_different_people():
    result = store()
    first = result.put_template_sync(template("One"), actor_pk="alice")
    second = result.put_template_sync(template("Two"), actor_pk="bob")
    assert {item["sk"] for item in result.table.items[(result.pk, result.INDEX_SK)]["templates"]} == {first, second}


def test_update_with_stale_revision_still_applies():
    result = store()
    seed(result)
    result.update_template_sync("template#1", template("Changed"), actor_pk="alice")
    assert result.table.items[(result.pk, "template#1")]["meta"]["name"] == "Changed"
    assert "revision" not in result.table.items[(result.pk, "template#1")]["meta"]


def test_sessions_only_update_keeps_description_and_phases(monkeypatch):
    from services.templates.template_update import core

    result = store()
    original = template("Candito")
    original["meta"]["description"] = "Original description"
    original["phases"] = [{"name": "Strength"}]
    seed(result, item=original)
    monkeypatch.setattr(core, "_get_template_store", lambda: result)

    asyncio.run(core.template_update("template#1", {"sessions": [{"day_of_week": "Thursday"}]}, "alice"))

    saved = result.get_template_sync("template#1", actor_pk="alice")
    assert saved["meta"]["name"] == "Candito"
    assert saved["meta"]["description"] == "Original description"
    assert saved["phases"] == [{"name": "Strength"}]
    assert saved["sessions"][0]["day_index"] == 4


def test_weekday_patch_uses_position_when_imported_ids_and_days_repeat(monkeypatch):
    from services.runtime.contract import load_operations
    from services.runtime.dispatch import dispatch
    from services.templates.template_patch import core

    result = store()
    original = template("Candito")
    original["phases"] = [{"name": "Strength"}]
    original["sessions"] = [
        {"id": "imported-1-1", "week_number": 1, "day_of_week": "Monday", "day_index": 1,
         "exercises": [{"name": exercise}]}
        for exercise in ("Squat", "Bench Press")
    ]
    seed(result, item=original)
    monkeypatch.setattr(core, "_get_template_store", lambda: result)
    arguments = {"sk": "template#1", "pk": "alice", "_person_pk": "alice",
                 "operations": [{"op": "set_session_weekdays", "weekdays": {"2": "Thursday"}}]}
    operation = load_operations("templates")["template_patch"]
    assert dispatch(operation, arguments)["applied"] is False
    assert result.get_template_sync("template#1", actor_pk="alice")["sessions"] == original["sessions"]
    assert dispatch(operation, {**arguments, "apply": True})["applied"] is True

    saved = result.get_template_sync("template#1", actor_pk="alice")
    assert saved["meta"]["name"] == "Candito"
    assert saved["phases"] == original["phases"]
    assert saved["sessions"] == [
        original["sessions"][0],
        {**original["sessions"][1], "day_of_week": "Thursday", "day_index": 4},
    ]
    with pytest.raises(ValueError, match="Session 3"):
        dispatch(operation, {**arguments, "apply": True, "operations": [
            {"op": "set_session_weekdays", "weekdays": {"1": "Tuesday", "3": "Friday"}},
        ]})
    assert result.get_template_sync("template#1", actor_pk="alice") == saved


def test_private_copy_cannot_be_replayed_or_retrieved_by_other_person():
    result = store()
    seed(result, item=template("Private", author="alice", published=False))
    with pytest.raises(Exception):
        result.copy_template_sync("template#1", "Copy", actor_pk="bob")


def test_template_applications_get_fresh_session_ids():
    blueprint = [{"id": "blueprint-session", "session_id": "blueprint-session", "date": "2026-09-15"}]
    first = _new_sessions(blueprint)
    second = _new_sessions(blueprint)
    assert first[0]["id"] == first[0]["session_id"]
    assert first[0]["id"] != second[0]["id"]
    assert blueprint[0]["id"] == "blueprint-session"


def test_template_apply_preserves_amrap_and_duration_without_inventing_loads():
    sessions = concretize({"sessions": [{"week_number": 1, "day_of_week": "Monday", "exercises": [
        {"name": "Leg Curl", "sets": 2, "reps": None, "rep_mode": "amrap", "load_type": "rpe", "rpe_target": 8, "notes": "finish safely"},
        {"name": "Air Bike", "sets": 1, "reps": None, "duration_minutes": 15, "load_type": "unresolvable", "notes": "easy"},
        {"name": "Timed Load", "sets": 2, "reps": None, "duration_minutes": 5, "load_type": "absolute", "load_value": 20},
    ]}]}, {}, [], __import__("datetime").date(2026, 8, 31))
    amrap, cardio, timed_load = sessions[0]["planned_exercises"]
    assert (amrap["rep_mode"], amrap["reps"], amrap["kg"], amrap["rpe_target"], amrap["notes"]) == ("amrap", None, None, 8, "finish safely")
    assert (cardio["duration_minutes"], cardio["reps"], cardio["kg"], cardio["rpe_target"]) == (15, None, None, None)
    assert (timed_load["duration_minutes"], timed_load["kg"]) == (5, 20)


def test_max_resolution_gate_requires_only_percentages():
    template = {"required_maxes": ["lift-rpe", "lift-percent"], "sessions": [{"exercises": [
        {"glossary_id": "lift-rpe", "load_type": "rpe"},
        {"glossary_id": "lift-amrap", "load_type": "rpe", "rep_mode": "amrap"},
        {"glossary_id": "lift-time", "load_type": "unresolvable", "duration_minutes": 15},
        {"glossary_id": "lift-percent", "load_type": "percentage"},
    ]}]}
    assert check_max_resolution_gate(template, {}, [
        {"id": "lift-rpe"}, {"id": "lift-amrap"}, {"id": "lift-time"}, {"id": "lift-percent"},
    ]) == ["lift-percent"]


def test_block_conversion_preserves_amrap_and_duration_without_fabricating_reps():
    converted = convert_block_to_template({"meta": {}, "sk": "program#1", "sessions": [{
        "date": "2026-09-01", "day": "Tuesday", "planned_exercises": [
            {"name": "Leg Curl", "sets": 2, "reps": None, "rep_mode": "amrap", "kg": None, "load_source": "unresolvable", "notes": "to failure"},
            {"name": "Stair Stepper", "sets": 1, "reps": None, "duration_minutes": 15, "kg": None, "load_source": "unresolvable"},
            {"name": "Loaded Bike", "sets": 1, "reps": None, "duration_minutes": 5, "kg": 20, "load_source": "absolute"},
        ]}]}, {})
    amrap, cardio, timed_load = converted["sessions"][0]["exercises"]
    assert (amrap["rep_mode"], amrap["reps"], amrap["notes"]) == ("amrap", None, "to failure")
    assert (cardio["duration_minutes"], cardio["reps"], cardio["load_type"], cardio["load_value"]) == (15, None, "unresolvable", None)
    assert (timed_load["duration_minutes"], timed_load["reps"], timed_load["load_type"], timed_load["load_value"]) == (5, None, "absolute", 20)


def test_template_apply_confirm_starts_one_new_block_and_keeps_existing_sessions(monkeypatch):
    core = __import__("services.templates.template_apply_confirm.core", fromlist=["core"])
    handler = __import__("services.templates.template_apply_confirm.handler", fromlist=["handler"])

    class Templates:
        async def get_template(self, _sk, actor_pk=None):
            return {"phases": [], "sessions": [{"id": "blueprint", "week_number": 1, "day_index": 1, "exercises": []}]}

    class Store:
        def __init__(self):
            self.program = {"meta": {"version_label": "1.0", "blocks": [{"id": "current", "status": "active"}]}, "current_maxes": {}, "sessions": [{"id": "external-session", "date": "2026-09-01", "status": "completed"}]}
            self.transitions = 0

        async def get_program(self):
            return copy.deepcopy(self.program)

        async def block_transition(self, action, block_id, **kwargs):
            assert action == "complete_and_start" and block_id == "current"
            self.transitions += 1
            self.program["sessions"] = self.program["sessions"] + kwargs["next_program"]["sessions"]
            self.program["meta"] = {"version_label": "2.0", "blocks": [{"id": "current", "status": "completed"}, {"id": "block-next", "status": "active"}], "current_block_id": "block-next"}
            return {"next_block_id": "block-next", "program": copy.deepcopy(self.program)}

    store = Store()
    monkeypatch.setattr(core, "_get_template_store", lambda: Templates())
    monkeypatch.setattr(core, "_get_store", lambda _actor: store)
    monkeypatch.setattr(core, "_get_glossary_store", lambda _actor: type("Glossary", (), {"get_glossary": lambda self: asyncio.sleep(0, result=[])})())
    event = {"sk": "template#1", "backfilled_maxes": {"squat": 100, "bench": 120}, "start_date": "2026-09-22", "week_start_day": "Monday", "target": "new_block"}
    body = json.loads(handler.handler(event, None)["body"])
    assert body["block_id"] == "block-next" and "revision" not in body
    assert store.transitions == 1
    assert any(item["id"] == "external-session" for item in store.program["sessions"])
