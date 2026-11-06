import copy
import asyncio
import json

import pytest


from services.lib.template_store import TemplateStore
from services.handlers.templates.template_apply_confirm.core import _new_sessions


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


def test_template_apply_confirm_starts_one_new_block_and_keeps_existing_sessions(monkeypatch):
    core = __import__("services.handlers.templates.template_apply_confirm.core", fromlist=["core"])
    handler = __import__("services.handlers.templates.template_apply_confirm.handler", fromlist=["handler"])

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
