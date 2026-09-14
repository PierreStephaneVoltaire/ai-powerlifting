import importlib
import httpx
import sys
from jsonschema import ValidationError
from types import SimpleNamespace

from services.contract import load_operations
from services.dispatch import dispatch


def test_analytics_contracts_have_structured_results():
    operations = load_operations("analytics")
    assert len(operations) == 31
    assert all(operation.result_schema for operation in operations.values())


def test_analysis_section_uses_supplied_snapshot(monkeypatch):
    core = importlib.import_module("lambda.pod_analysis.handlers.analysis_section.core")
    monkeypatch.setattr(core, "_get_glossary_sync", lambda _table: [])
    result = dispatch(
        load_operations("analytics")["analysis_section"],
        {
            "pk": "athlete-1",
            "program": {"meta": {"program_start": "2026-01-01"}, "sessions": []},
            "section": "overview",
            "ref_date": "2026-01-07",
        },
    )
    assert "current_maxes" in result
    assert result["sessions_analyzed"] == 0


def test_shared_lift_calculations_are_used_by_analytics():
    analytics = importlib.import_module("lambda.get_analysis_markdown.analytics")
    calculations = importlib.import_module("lift_calculations")
    assert analytics.estimate_1rm(100, 5, 8) == calculations.estimate_1rm(100, 5, 8)
    assert analytics.calculate_dots(500, 80, "male") == calculations.calculate_dots(500, 80, "male")


def test_internal_e1rm_keeps_precision_before_regression():
    analytics = importlib.import_module("lambda.get_analysis_markdown.analytics")
    calculations = importlib.import_module("lift_calculations")
    assert calculations.estimate_1rm_value(100, 3, 8) == 100 / 0.875
    assert analytics._estimate_e1rm_from_set(100, 3, 8) == 114.28571428571429
    assert calculations.estimate_1rm(100, 3, 8)["e1rm"] == 114.3


def test_e1rm_multiplier_suggestions_binding_uses_existing_calculation():
    result = dispatch(
        load_operations("analytics")["health_suggest_e1rm_multipliers"],
        {
            "pk": "athlete-1",
            "program": {"sessions": [], "competitions": [], "lift_profiles": []},
            "max_history": [],
            "reference_date": "2026-09-13",
        },
    )
    assert result == {"squat": None, "bench": None, "deadlift": None}


def test_composite_operation_bindings_proxy_to_node_sidecar(monkeypatch):
    composite = importlib.import_module("lambda.get_analysis_markdown.composite")
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"data": {"schemaVersion": 6}, "error": None}, request=httpx.Request("POST", url))

    monkeypatch.setattr(composite.httpx, "post", fake_post)
    result = composite.call_node("analytics.manifest", {"pk": "athlete-1", "window": "current"})
    assert result == {"schemaVersion": 6}
    assert calls[0][0].endswith("/internal/analytics/operations/analytics.manifest")
    assert calls[0][1]["headers"]["X-Athlete-Pk"] == "athlete-1"


def test_composite_proxy_preserves_authenticated_person_without_forwarding_it_as_input(monkeypatch):
    composite = importlib.import_module("lambda.get_analysis_markdown.composite")
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"data": {"schemaVersion": 6}, "error": None}, request=httpx.Request("POST", url))

    monkeypatch.setattr(composite.httpx, "post", fake_post)
    composite.call_node("analytics.manifest", {"pk": "athlete-1", "_person_pk": "coach-1", "_if_job_id": "job-1"})
    headers = calls[0][1]["headers"]
    assert headers["X-Person-Pk"] == "coach-1"
    assert headers["X-IF-Turn-Id"] == "job-1"
    assert calls[0][1]["json"] == {"pk": "athlete-1"}


def test_composite_operation_contracts_have_importable_handlers():
    operations = load_operations("analytics")
    names = {name for name in operations if name.startswith("analytics.")}
    assert names == {
        "analytics.manifest",
        "analytics.sections_queue",
        "analytics.sections_get",
        "analytics.sections_invalidate",
        "analytics.weekly",
        "analytics.bundle",
        "analytics.regenerate",
        "analytics.markdown",
        "analytics.blocks_list",
        "analytics.blocks_get",
        "analytics.blocks_regenerate",
        "analytics.block_evaluation",
        "analytics.correlation",
        "analytics.export",
        "analytics.compare",
        "analytics.compare_ai",
    }
    for operation in names:
        module = importlib.import_module(operations[operation].handler)
        assert callable(module.handler)


def test_composite_inputs_match_their_routes():
    operations = load_operations("analytics")
    expected = {
        "analytics.manifest": {"pk", "asOfDate", "window"},
        "analytics.sections_queue": {"pk", "asOfDate", "window", "sections", "read_only"},
        "analytics.sections_get": {"pk", "asOfDate", "window", "sectionKey"},
        "analytics.sections_invalidate": {"pk", "asOfDate", "window", "sections"},
        "analytics.weekly": {"pk", "weeks", "block", "windowStart", "windowEnd", "refDate", "weekStart", "weekEnd"},
        "analytics.bundle": {"pk", "asOfDate", "refresh"},
        "analytics.blocks_list": {"pk"},
        "analytics.blocks_get": {"pk", "blockKey", "refresh"},
        "analytics.blocks_regenerate": {"pk", "blockKey"},
        "analytics.block_evaluation": {"pk", "blockKey", "refresh", "cacheOnly"},
        "analytics.correlation": {"pk", "blockKey", "refresh", "cacheOnly"},
        "analytics.export": {"pk", "blockKey", "format"},
        "analytics.compare": {"pk", "blockKeys"},
        "analytics.compare_ai": {"pk", "blockKeys", "refresh", "cacheOnly", "read_only"},
        "analytics.regenerate": {"pk", "asOfDate", "window", "windows", "sections"},
        "analytics.markdown": {"pk", "refresh", "max_age_hours"},
    }
    for name, fields in expected.items():
        schema = operations[name].input_schema
        assert set(schema["properties"]) == fields
        assert schema["additionalProperties"] is False
        try:
            operations[name].validate_input({"pk": "athlete-1", "unexpected": True})
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{name} accepts an unrelated input field")


def test_composite_ai_report_results_have_concrete_shapes():
    operations = load_operations("analytics")
    operations["analytics.block_evaluation"].validate_result({"stance": "continue", "summary": "Stable"})
    operations["analytics.correlation"].validate_result({"findings": [], "summary": "Stable"})


def test_markdown_export_formatter_remains_available_to_lazy_report_imports(tmp_path):
    export = importlib.import_module("lambda.get_analysis_markdown.export")
    output = tmp_path / "program.md"
    export.build_program_markdown(
        {"meta": {"program_name": "Athlete A"}, "sessions": [], "phases": [], "goals": [], "competitions": []},
        str(output),
        analysis={"weekly": {}},
        export_context={"pk": "athlete-a"},
    )
    assert output.read_text(encoding="utf-8").startswith("# Athlete A")


def test_markdown_report_handler_lazily_loads_the_restored_formatter(monkeypatch):
    core = importlib.import_module("lambda.get_analysis_markdown.core")
    writes = []

    class Store:
        pk = "athlete-a"

        def invalidate_cache(self):
            return None

        async def get_program(self):
            return {"meta": {"program_name": "Athlete A"}, "sessions": [], "phases": [], "goals": [], "competitions": []}

    class Glossary:
        async def get_glossary(self):
            return []

    class Table:
        def put_item(self, **kwargs):
            writes.append(kwargs["Item"])

    monkeypatch.setattr(core, "_get_store", Store)
    monkeypatch.setattr(core, "_get_glossary_store", Glossary)
    monkeypatch.setattr(core, "_build_sectioned_week_analysis", lambda *args, **kwargs: {})
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(resource=lambda *args, **kwargs: SimpleNamespace(Table=lambda _name: Table())))
    monkeypatch.setitem(sys.modules, "analysis_cache", SimpleNamespace(AnalysisCacheStore=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("cache unavailable"))))

    result = core.get_analysis_markdown({"pk": "athlete-a"})
    assert result["markdown"].startswith("# Athlete A")
    assert writes[0]["pk"] == "analysis#athlete-a"
