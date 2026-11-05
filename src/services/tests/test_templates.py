import asyncio
import importlib
import json
import sys
import unittest
from datetime import date, timedelta
from types import ModuleType
from unittest.mock import patch

from jsonschema import ValidationError

from services.contract import load_operations


class FakeTemplateStore:
    def __init__(self):
        self.templates = {}

    async def put_template(self, template, **kwargs):
        self.templates["template#1"] = {**template, "pk": "athlete-1", "sk": "template#1"}
        return "template#1"

    async def get_template(self, sk, **kwargs):
        return self.templates.get(sk)

    async def set_evaluation(self, sk, evaluation, actor_pk=None, program_context=None):
        self.templates[sk]["meta"]["ai_evaluation"] = evaluation
        self.templates[sk]["meta"]["program_context"] = program_context
        self.evaluated_by = actor_pk


class FakeProgramStore:
    pk = "athlete-1"

    def __init__(self):
        self.program = {"meta": {}, "current_maxes": {"squat": 200}}
        self.saved = None

    async def get_program(self):
        return self.program

    async def _write_new_version(self, program, minor=False, expected_revision=None, idempotency_key=None):
        self.saved = program
        return program


class FakeGlossaryStore:
    async def get_glossary(self):
        return []


class TemplateContractTests(unittest.TestCase):
    def test_inventory_and_required_mutation_fields(self):
        operations = load_operations("templates")
        self.assertEqual(len(operations), 15)
        for name in ("template_archive", "template_publish", "template_unpublish", "template_apply_confirm"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    operations[name].validate_input({})
        operations["template_create_blank"].validate_result({"status": "created", "sk": "template#1"})

    def test_blank_creation_handler_returns_domain_result(self):
        module = importlib.import_module("services.handlers.templates.template_create_blank.core")
        handler = importlib.import_module("services.handlers.templates.template_create_blank.handler")
        store = FakeTemplateStore()
        with patch.object(module, "_get_template_store", return_value=store):
            result = handler.handler({"name": "Strength", "pk": "athlete-1", "expected_revision": 0, "idempotency_key": "create-strength"}, None)
        body = json.loads(result["body"])
        self.assertEqual(body, {"status": "created", "sk": "template#1"})
        self.assertEqual(store.templates["template#1"]["meta"]["name"], "Strength")

    def test_apply_handler_writes_template_lineage(self):
        apply_core = importlib.import_module("services.handlers.templates.template_apply_confirm.core")
        apply_handler = importlib.import_module("services.handlers.templates.template_apply_confirm.handler")
        template_store = FakeTemplateStore()
        program_store = FakeProgramStore()
        template_store.templates["template#1"] = {"sk": "template#1", "meta": {"name": "Strength"}, "phases": [], "sessions": []}
        with patch.object(apply_core, "_get_template_store", return_value=template_store), patch.object(apply_core, "_get_store", return_value=program_store), patch.object(apply_core, "_get_glossary_store", return_value=FakeGlossaryStore()):
            result = apply_handler.handler({"sk": "template#1", "start_date": "2026-09-14", "expected_revision": 0, "idempotency_key": "template-apply"}, None)
        self.assertEqual(json.loads(result["body"])["status"], "applied")
        self.assertEqual(program_store.saved["meta"]["template_lineage"]["applied_template_sk"], "template#1")

    def test_template_mutations_require_revision_and_idempotency_envelope(self):
        operations = load_operations("templates")
        for name, payload in {
            "template_apply": {"sk": "template#1"},
            "template_apply_confirm": {"sk": "template#1"},
        }.items():
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    operations[name].validate_input(payload)

    def test_template_mutation_results_require_authoritative_revision(self):
        operations = load_operations("templates")
        results = {
            "template_archive": {"status": "archived", "sk": "template#1", "revision": 1},
            "template_unarchive": {"status": "unarchived", "sk": "template#1", "revision": 2},
            "template_publish": {"status": "published", "sk": "template#1", "revision": 3},
            "template_unpublish": {"status": "unpublished", "sk": "template#1", "revision": 4},
            "template_update": {"status": "updated", "sk": "template#1", "revision": 5},
            "template_copy": {"status": "copied", "new_sk": "template#2", "revision": 0},
            "template_apply_confirm": {"status": "applied", "program_version": "v002", "program_sk": "program#v002", "revision": 6},
        }
        for name, result in results.items():
            with self.subTest(name=name):
                operations[name].validate_result(result)
                missing = dict(result)
                missing.pop("revision")
                with self.assertRaises(ValidationError):
                    operations[name].validate_result(missing)

    def _evaluate(self, program, entries, **extra):
        core = importlib.import_module("services.handlers.templates.template_evaluate.core")
        entries_module = importlib.import_module("services.lib.competition_entries")
        template_store = FakeTemplateStore()
        template_store.templates["template#1"] = {"sk": "template#1", "meta": {"name": "Strength"}, "sessions": [{"week_number": 1, "date": "2027-01-02", "exercises": []}, {"week_number": 4, "date": "2027-01-23", "exercises": [{"name": "Squat", "sets": 1, "reps": 1}]}]}
        program_store = FakeProgramStore()
        program_store.program = program
        captured = {}

        async def evaluate(stripped, athlete_context, metrics, context):
            captured.update(athlete_context)
            captured["template"] = stripped
            captured["context"] = context
            return {"stance": "monitor", "summary": "ok", "strengths": [], "weaknesses": [], "suggestions": []}

        ai = ModuleType("template_evaluate_ai")
        ai.generate_template_evaluate_report = evaluate
        with patch.object(core, "_get_template_store", return_value=template_store), patch.object(core, "_get_program_store", return_value=program_store), patch.object(core, "_get_glossary", return_value=[]), patch.object(core, "_specificity_band", return_value=lambda weeks_out: None), patch.object(entries_module, "load_entries", return_value=entries), patch.dict(sys.modules, {"services.handlers.templates.template_evaluate.template_evaluate_ai": ai}):
            report = core.template_evaluate({"pk": "athlete-1", "actor_pk": "person-1", "sk": "template#1", **extra})
        return captured, template_store, report

    def test_evaluate_counts_weeks_to_the_next_confirmed_competition_and_saves_the_report(self):
        future = (date.today() + timedelta(days=70)).isoformat()
        program = {
            "meta": {"sex": "male", "current_body_weight_kg": 100, "comp_date": (date.today() - timedelta(days=70)).isoformat()},
            "current_maxes": {"squat": 200, "bench": 150, "deadlift": 250},
        }
        entries = [
            {"sk": "COMP#past", "name": "Old Meet", "start_date": (date.today() - timedelta(days=7)).isoformat(), "user_status": "confirmed"},
            {"sk": "COMP#skip", "name": "Maybe Meet", "start_date": (date.today() + timedelta(days=14)).isoformat(), "user_status": "available"},
            {"sk": "COMP#optional", "name": "WRPF Nationals 2026", "start_date": (date.today() + timedelta(days=4)).isoformat(), "user_status": "optional"},
            {"sk": "COMP#next", "name": "Royal City Rumble 5", "start_date": future, "user_status": "confirmed"},
        ]
        captured, store, report = self._evaluate(program, entries, context="Overreach with separate lift progressions")
        self.assertNotIn("dots_score", captured)
        self.assertEqual(captured["timeline"], {"template_weeks": 4, "next_confirmed_competition": {"name": "Royal City Rumble 5", "weeks_away": 10.0}, "weeks_until_template_must_start": 6.0})
        self.assertEqual(captured["context"], "Overreach with separate lift progressions")
        self.assertNotIn("date", captured["template"]["sessions"][0])
        self.assertEqual(store.templates["template#1"]["meta"]["ai_evaluation"], report)
        self.assertEqual(store.templates["template#1"]["meta"]["program_context"], "Overreach with separate lift progressions")
        self.assertEqual(store.evaluated_by, "person-1")

    def test_evaluate_ignores_a_past_meta_comp_date_when_no_competition_is_upcoming(self):
        program = {"meta": {"comp_date": (date.today() - timedelta(days=73)).isoformat()}, "current_maxes": {}}
        captured, _, _ = self._evaluate(program, [])
        self.assertEqual(captured["timeline"], {"template_weeks": 4, "next_confirmed_competition": None})


if __name__ == "__main__":
    unittest.main()


def test_template_evaluation_prompt_accepts_dynamodb_decimals():
    import asyncio
    import json
    from decimal import Decimal

    module = importlib.import_module("services.handlers.templates.template_evaluate.template_evaluate_ai")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            arguments = {"stance": "solid", "summary": "ok", "strengths": [], "weaknesses": [], "suggestions": [], "projected_readiness_at_comp": 0.8}
            return {"choices": [{"message": {"tool_calls": [{"function": {"arguments": json.dumps(arguments)}}]}}]}

    async def completion(payload):
        captured["user"] = payload["messages"][1]["content"]
        return Response()

    template = {"meta": {"estimated_weeks": Decimal("12")}, "sessions": [{"exercises": [{"sets": Decimal("3"), "load_value": Decimal("0.75")}]}]}
    with patch.object(module, "completion", completion):
        report = asyncio.run(module.generate_template_evaluate_report(template, {"bodyweight_kg": Decimal("82.5")}))

    payload = json.loads(captured["user"])
    assert payload["template"]["meta"]["estimated_weeks"] == 12
    assert payload["template"]["sessions"][0]["exercises"][0]["load_value"] == 0.75
    assert payload["athlete_context"]["bodyweight_kg"] == 82.5
    assert report["stance"] == "solid"


def test_set_evaluation_updates_only_the_evaluation_field_for_the_owner():
    from decimal import Decimal
    from unittest.mock import MagicMock
    import pytest
    from services.lib.template_store import TemplateStore

    store = TemplateStore("if-health-templates")
    table = MagicMock()
    store._table = table
    store.get_template_sync = lambda sk, actor_pk=None: {"sk": sk, "meta": {"author_pk": "person-1"}}
    store.set_evaluation_sync("template#1", {"stance": "monitor", "score": 0.5}, actor_pk="person-1")
    call = table.update_item.call_args.kwargs
    assert call["Key"] == {"pk": "template_library", "sk": "template#1"}
    assert call["ExpressionAttributeNames"]["#evaluation"] == "ai_evaluation"
    assert call["ExpressionAttributeValues"][":evaluation"]["score"] == Decimal("0.5")
    assert call["ExpressionAttributeValues"][":context"] == ""
    store.set_evaluation_sync("template#1", {"stance": "monitor"}, actor_pk="person-1", program_context="overreach")
    assert table.update_item.call_args.kwargs["ExpressionAttributeValues"][":context"] == "overreach"
    with pytest.raises(Exception):
        store.set_evaluation_sync("template#1", {"stance": "x"}, actor_pk="someone-else")


def test_delete_template_removes_item_and_index_entry_for_the_owner_only():
    from unittest.mock import MagicMock
    import pytest
    from services.lib.template_store import TemplateStore

    store = TemplateStore("if-health-templates")
    table = MagicMock()
    store._table = table
    store.get_template_sync = lambda sk, actor_pk=None, include_hidden=False: {"sk": sk, "meta": {"author_pk": "person-1"}}
    store._read_index_item_sync = lambda: {"templates": [{"sk": "template#1"}, {"sk": "template#2"}]}
    written = []
    store._write_index_sync = lambda templates, updated_at=None: written.append(templates)

    with pytest.raises(Exception):
        store.delete_template_sync("template#1", actor_pk="someone-else")
    table.delete_item.assert_not_called()

    assert store.delete_template_sync("template#1", actor_pk="person-1") == {"status": "deleted", "sk": "template#1"}
    table.delete_item.assert_called_once_with(Key={"pk": "template_library", "sk": "template#1"})
    assert written == [[{"sk": "template#2"}]]


def test_delete_requires_an_acting_person_and_is_hidden_from_the_coach():
    import pytest
    from services.access import permission_map
    from services.handlers.templates.template_delete.core import template_delete

    with pytest.raises(ValueError, match="Verified acting Person"):
        asyncio.run(template_delete("template#1", None))
    assert permission_map()["template_delete"] == {"permission": "templates:write", "internal_only": True}
