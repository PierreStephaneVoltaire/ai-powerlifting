import importlib
import json
from decimal import Decimal

import pytest


@pytest.mark.parametrize("module_name, function_name", [
    ("services.handlers.health.get_diet_notes.handler", "health_get_diet_notes"),
    ("services.handlers.health.get_supplements.handler", "health_get_supplements"),
    ("services.handlers.program.health_invalidate_program_cache.handler", "health_invalidate_program_cache"),
])
def test_handlers_serialize_decimals(monkeypatch, module_name, function_name):
    module = importlib.import_module(module_name)
    payload = {"kg": Decimal("102.5"), "sets": Decimal("3")}

    async def async_result(_args):
        return payload

    original = getattr(module, function_name)
    replacement = async_result if importlib.import_module("inspect").iscoroutinefunction(original) else (lambda _args: payload)
    monkeypatch.setattr(module, function_name, replacement)
    response = module.handler({"args": {}}, None)
    assert json.loads(response["body"]) == {"kg": 102.5, "sets": 3}


def test_markdown_export_resolves_dynamodb_resource():
    core = importlib.import_module("services.handlers.program.export_program_markdown.core")
    assert callable(core.dynamodb_resource)
