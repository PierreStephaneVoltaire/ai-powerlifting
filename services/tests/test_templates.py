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


class FakeProgramStore:
    pk = "athlete-1"

    def __init__(self):
        self.program = {"meta": {}, "current_maxes": {"squat": 200}}
        self.saved = None

    async def get_program(self):
        return self.program

    async def _write_new_version(self, program, minor=False):
        self.saved = program


class FakeGlossaryStore:
    async def get_glossary(self):
        return []


class TemplateContractTests(unittest.TestCase):
    def test_inventory_and_required_mutation_fields(self):
        operations = load_operations("templates")
        self.assertEqual(len(operations), 14)
        for name in ("template_archive", "template_publish", "template_unpublish", "template_apply_confirm"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    operations[name].validate_input({})
        operations["template_create_blank"].validate_result({"status": "created", "sk": "template#1"})

    def test_blank_creation_handler_returns_domain_result(self):
        module = importlib.import_module("lambda.pod_templates.handlers.template_create_blank.core")
        handler = importlib.import_module("lambda.pod_templates.handlers.template_create_blank.handler")
        store = FakeTemplateStore()
        with patch.object(module, "_get_template_store", return_value=store):
            result = handler.handler({"name": "Strength", "pk": "athlete-1"}, None)
        body = json.loads(result["body"])
        self.assertEqual(body, {"status": "created", "sk": "template#1"})
        self.assertEqual(store.templates["template#1"]["meta"]["name"], "Strength")

    def test_apply_handler_writes_template_lineage(self):
        apply_core = importlib.import_module("lambda.pod_templates.handlers.template_apply_confirm.core")
        apply_handler = importlib.import_module("lambda.pod_templates.handlers.template_apply_confirm.handler")
        template_store = FakeTemplateStore()
        program_store = FakeProgramStore()
        template_store.templates["template#1"] = {"sk": "template#1", "meta": {"name": "Strength"}, "phases": [], "sessions": []}
        with patch.object(apply_core, "_get_template_store", return_value=template_store), patch.object(apply_core, "_get_store", return_value=program_store), patch.object(apply_core, "_get_glossary_store", return_value=FakeGlossaryStore()):
            result = apply_handler.handler({"sk": "template#1", "start_date": "2026-09-14"}, None)
        self.assertEqual(json.loads(result["body"])["status"], "applied")
        self.assertEqual(program_store.saved["meta"]["template_lineage"]["applied_template_sk"], "template#1")

    def test_evaluate_uses_program_competition_context(self):
        core = importlib.import_module("lambda.pod_templates.handlers.template_evaluate.core")
        template_store = FakeTemplateStore()
        template_store.templates["template#1"] = {"sk": "template#1", "meta": {"name": "Strength"}}
        program_store = FakeProgramStore()
        program_store.program = {
            "meta": {"sex": "male", "current_body_weight_kg": 100, "comp_date": (date.today() + timedelta(days=70)).isoformat()},
            "current_maxes": {"squat": 200, "bench": 150, "deadlift": 250},
        }
        captured = {}

        async def evaluate(_template, athlete_context):
            captured.update(athlete_context)
            return {"stance": "monitor", "summary": "ok", "strengths": [], "weaknesses": [], "suggestions": [], "projected_readiness_at_comp": 50}

        ai = ModuleType("template_evaluate_ai")
        ai.generate_template_evaluate_report = evaluate
        with patch.object(core, "_get_template_store", return_value=template_store), patch.object(core, "_get_program_store", return_value=program_store), patch.dict(sys.modules, {"lambda.pod_templates.handlers.template_evaluate.template_evaluate_ai": ai}):
            core.template_evaluate({"pk": "athlete-1", "sk": "template#1"})
        self.assertEqual(captured["dots_score"], 369.31)
        self.assertEqual(captured["weeks_to_comp"], 10.0)


if __name__ == "__main__":
    unittest.main()
