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


def test_composite_block_cache_miss_preserves_not_found_status(monkeypatch):
    composite = importlib.import_module("lambda.get_analysis_markdown.composite")
    from services.dispatch import OperationError

    def fake_post(url, **kwargs):
        return httpx.Response(404, json={"data": None, "error": "Block current not found"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(composite.httpx, "post", fake_post)
    try:
        composite.call_node("analytics.blocks_get", {"pk": "athlete-1", "blockKey": "current", "cacheOnly": True})
    except OperationError as error:
        assert error.status == 404
        assert error.code == "cache_miss"
    else:
        raise AssertionError("cache miss must preserve 404")


def test_composite_correlation_cache_miss_preserves_not_found_status(monkeypatch):
    composite = importlib.import_module("lambda.get_analysis_markdown.composite")
    from services.dispatch import OperationError

    def fake_post(url, **kwargs):
        return httpx.Response(404, json={"data": None, "error": "Correlation report not found"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(composite.httpx, "post", fake_post)
    try:
        composite.call_node("analytics.correlation", {"pk": "athlete-1", "blockKey": "unknown", "cacheOnly": True})
    except OperationError as error:
        assert error.status == 404
        assert error.code == "cache_miss"
        assert str(error) == "Correlation report not found"
    else:
        raise AssertionError("cache miss must preserve 404")


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


def test_analysis_section_accepts_alert_list_from_handler():
    operation = load_operations("analytics")["analysis_section"]
    operation.validate_result({"alerts": [{"severity": "info", "source": "test", "message": "ok"}], "flags": []})


def test_weekly_analysis_accepts_alert_list_from_handler():
    operation = load_operations("analytics")["weekly_analysis"]
    operation.validate_result({"alerts": [{"severity": "info", "source": "test", "message": "ok"}], "flags": []})


def test_legacy_weekly_contract_matches_flat_handler_result(monkeypatch):
    operation = load_operations("analytics")["analytics.weekly"]
    flat_result = {
            "week": 1,
            "block": "current",
            "lifts": {},
            "fatigue_index": None,
            "fatigue_components": None,
            "compliance": {},
            "current_maxes": {},
            "estimated_dots": None,
            "projections": [],
            "projection_reason": None,
            "flags": [],
            "sessions_analyzed": 0,
            "exercise_stats": {},
            "alerts": [{"severity": "info", "source": "test", "message": "ok"}],
            "specificity_target_competition": None,
            "banister": None,
            "monotony_strain": None,
            "decoupling": None,
            "taper_quality": None,
        }
    operation.validate_result(flat_result)

    composite = importlib.import_module("lambda.get_analysis_markdown.composite")
    monkeypatch.setattr(composite, "call_node", lambda _operation, _args: flat_result)
    assert dispatch(operation, {"pk": "athlete-1"}) == flat_result


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
        "analytics.blocks_get": {"pk", "blockKey", "refresh", "cacheOnly"},
        "analytics.blocks_regenerate": {"pk", "blockKey"},
        "analytics.block_evaluation": {"pk", "blockKey", "refresh", "cacheOnly"},
        "analytics.correlation": {"pk", "blockKey", "refresh", "cacheOnly"},
        "analytics.export": {"pk", "blockKey", "format"},
        "analytics.compare": {"pk", "blockKeys"},
        "analytics.compare_ai": {"pk", "blockKeys", "refresh", "cacheOnly", "read_only"},
        "analytics.regenerate": {"pk", "asOfDate", "window", "windows", "sections"},
        "analytics.markdown": {"pk", "refresh", "cache_only", "max_age_hours"},
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

        def query(self, **kwargs):
            return {'Items': []}

    monkeypatch.setattr(core, "_get_store", Store)
    monkeypatch.setattr(core, "_get_glossary_store", Glossary)
    monkeypatch.setattr(core, "_build_sectioned_week_analysis", lambda *args, **kwargs: {})
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(resource=lambda *args, **kwargs: SimpleNamespace(Table=lambda _name: Table())))
    monkeypatch.setitem(sys.modules, "analysis_cache", SimpleNamespace(AnalysisCacheStore=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("cache unavailable"))))

    result = core.get_analysis_markdown({"pk": "athlete-a"})
    assert result["markdown"].startswith("# Athlete A")
    assert writes[0]["pk"] == "analysis#athlete-a"


def test_markdown_cache_only_returns_a_miss_without_regenerating(monkeypatch):
    core = importlib.import_module("lambda.get_analysis_markdown.core")

    class Store:
        pk = "athlete-a"

    class CacheStore:
        def __init__(self, **kwargs):
            pass

        def get_markdown_cache(self, window):
            return None

        def get_markdown_dirty(self, window):
            return False

    monkeypatch.setattr(core, "_get_store", Store)
    monkeypatch.setattr(core, "_regenerate_analysis", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cache-only regenerated")))
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(resource=lambda *args, **kwargs: SimpleNamespace(Table=lambda _name: None)))
    monkeypatch.setitem(sys.modules, "analysis_cache", SimpleNamespace(AnalysisCacheStore=CacheStore))

    assert core.get_analysis_markdown({"pk": "athlete-a", "cache_only": True}) == {"cached": False, "cache_miss": True}


def test_markdown_dispatch_scopes_delegated_documents_and_rechecks_access(monkeypatch):
    core = importlib.import_module("lambda.get_analysis_markdown.core")
    records = {}
    analysis_inputs = []
    glossary_reads = []

    class Store:
        pk = "athlete-a"

        def invalidate_cache(self):
            return None

        async def get_program(self):
            return {
                "meta": {"program_name": "Visible", "training_notes": ["private profile note"], "current_body_weight_kg": 90},
                "settings": {"sex": "female", "private_setting": "private value"},
                "phases": [{"name": "Private phase", "block": "current"}],
                "sessions": [{"date": "2026-09-14", "block": "current", "session_notes": "visible session"}],
                "goals": [{"title": "Private goal", "priority": "primary"}],
                "diet_notes": [{"date": "2026-09-14", "notes": "private diet"}],
                "supplements": [{"name": "private supplement"}],
                "lift_profiles": [{"lift": "squat", "style": "private style"}],
                "competitions": [],
            }

    class Glossary:
        async def get_glossary(self):
            glossary_reads.append(True)
            return [{"term": "private glossary"}]

    class CacheStore:
        def __init__(self, **kwargs):
            pass

        def get_markdown_cache(self, block_key):
            return records.get(block_key)

        def get_markdown_dirty(self, block_key):
            return False

        def put_markdown_cache(self, markdown, block_key, access_requirements=None):
            records[block_key] = {"markdown": markdown, "generated_at": "2026-09-14T12:00:00+00:00", "access_requirements": access_requirements}

    monkeypatch.setattr(core, "_get_store", Store)
    monkeypatch.setattr(core, "_get_glossary_store", Glossary)
    def build_analysis(program, sessions, glossary, **kwargs):
        analysis_inputs.append((program, sessions, glossary))
        return {}

    monkeypatch.setattr(core, "_build_sectioned_week_analysis", build_analysis)
    import boto3
    monkeypatch.setattr(boto3, "resource", lambda *args, **kwargs: SimpleNamespace(Table=lambda _name: None))
    monkeypatch.setitem(sys.modules, "competition_entries", SimpleNamespace(with_competition_entries=lambda program, *args: program))
    monkeypatch.setitem(sys.modules, "analysis_cache", SimpleNamespace(AnalysisCacheStore=CacheStore))

    access = {"is_self": False, "permissions": ["analytics:write", "sessions:read"]}
    operations = load_operations("analytics")
    result = dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "refresh": True, "_access": access})
    assert "# Training Program" in result["markdown"]
    assert "visible session" in result["markdown"]
    assert "**Sex:** Undisclosed" in result["markdown"]
    for private in ("private profile note", "Private phase", "Private goal", "private diet", "private supplement", "private style"):
        assert private not in result["markdown"]
    assert analysis_inputs[-1][0]["settings"] == {}
    assert analysis_inputs[-1][2] == []
    assert not glossary_reads
    assert result["cached"] is False

    permitted = {"is_self": False, "permissions": ["analytics:write", "sessions:read", "profile:read", "glossary:read"]}
    permitted_result = dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "refresh": True, "_access": permitted})
    assert "**Sex:** Female" in permitted_result["markdown"]
    assert analysis_inputs[-1][0]["settings"] == {"sex": "female"}
    assert analysis_inputs[-1][2] == [{"term": "private glossary"}]
    assert len(glossary_reads) == 1

    cached = dispatch(operations["get_analysis_markdown"], {"pk": "athlete-a", "cache_only": True, "_access": access})
    assert cached["markdown"] == result["markdown"] and cached["cached"] is True

    records["current"] = {"markdown": "# Private legacy report", "generated_at": "2026-09-14T12:00:00+00:00"}
    for isolated in (
        {"is_self": False, "permissions": ["analytics:read"]},
        {"is_self": False, "permissions": ["analytics:read", "profile:read", "sessions:read"]},
    ):
        assert dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "cache_only": True, "_access": isolated}) == {"cached": False, "cache_miss": True}

    read_access = {"is_self": False, "permissions": ["analytics:read", "sessions:read"]}
    cached_again = dispatch(operations["get_analysis_markdown"], {"pk": "athlete-a", "cache_only": True, "_access": read_access})
    assert cached_again["markdown"] == result["markdown"] and cached_again["cached"] is True

    import pytest
    broader_access = {"is_self": False, "permissions": ["analytics:read", "sessions:read", "goals:read"]}
    read_cache_key = core._markdown_cache_key({"_access": read_access})
    records.pop(read_cache_key)
    records[core._markdown_cache_key({"_access": broader_access})] = {"markdown": "# Broad report", "generated_at": "2026-09-14T12:00:00+00:00", "access_requirements": {"permissions": ["sessions:read", "goals:read"], "competition_ids": []}}
    assert dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "cache_only": True, "_access": read_access}) == {"cached": False, "cache_miss": True}

    read_cache_key = core._markdown_cache_key({"_access": read_access})
    records[read_cache_key] = {**cached, "access_requirements": {"permissions": ["sessions:read", "goals:read"], "competition_ids": []}}
    assert read_cache_key in records
    with pytest.raises(Exception, match="Access to this saved result has changed"):
        dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "cache_only": True, "_access": read_access})


def test_markdown_dispatch_preserves_athlete_cache_reads(monkeypatch):
    core = importlib.import_module("lambda.get_analysis_markdown.core")

    class Store:
        pk = "athlete-a"

    class CacheStore:
        def __init__(self, **kwargs):
            pass

        def get_markdown_cache(self, window):
            return {"markdown": "# Full private report", "generated_at": "2026-09-14T12:00:00+00:00"}

        def get_markdown_dirty(self, window):
            return False

    monkeypatch.setattr(core, "_get_store", Store)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(resource=lambda *args, **kwargs: SimpleNamespace(Table=lambda _name: None)))
    monkeypatch.setitem(sys.modules, "analysis_cache", SimpleNamespace(AnalysisCacheStore=CacheStore))
    operations = load_operations("analytics")
    for name in ("analytics.markdown", "get_analysis_markdown"):
        result = dispatch(operations[name], {"pk": "athlete-a", "cache_only": True, "_access": {"is_self": True}})
        assert result["markdown"] == "# Full private report" and result["cached"] is True
