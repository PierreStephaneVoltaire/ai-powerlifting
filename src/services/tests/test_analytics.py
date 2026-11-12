import importlib
import httpx
import sys
from jsonschema import ValidationError
from types import SimpleNamespace

from services.contract import load_operations
from services.dispatch import dispatch


def test_analytics_contracts_have_structured_results():
    operations = load_operations("analytics")
    assert len(operations) == 27
    assert all(operation.result_schema for operation in operations.values())


def test_rankings_operations_live_in_their_own_domain():
    rankings = load_operations("rankings")
    assert set(rankings) == {"analyze_powerlifting_stats", "powerlifting_filter_categories", "powerlifting_ranking_percentile"}
    assert not set(rankings) & set(load_operations("analytics"))


def test_ranking_percentiles_are_cached_per_dataset_athlete_numbers_and_filter(monkeypatch):
    handler = importlib.import_module("services.handlers.analysis.powerlifting_ranking_percentile.handler")
    records = {}
    computed = []
    identity = ["dataset-a"]
    monkeypatch.setattr(handler, "load_data", lambda: object())
    monkeypatch.setattr(handler.opl_dataset, "identity", lambda: identity[0])
    monkeypatch.setattr(handler.valkey, "get_json", records.get)
    monkeypatch.setattr(handler.valkey, "set_json", records.__setitem__)
    monkeypatch.setattr(handler, "compute_ranking_percentiles", lambda _df, **kwargs: computed.append(kwargs) or {"global": {"total": len(computed)}})
    args = {"pk": "athlete-a", "squat_kg": 200, "bench_kg": 130, "deadlift_kg": 250, "bodyweight_kg": 82, "sex_code": "M", "equipment": "Raw"}

    assert handler.handler({"args": args}, None)["body"] == handler.handler({"args": args}, None)["body"]
    assert len(computed) == 1
    handler.handler({"args": {**args, "equipment": "Wraps"}}, None)
    handler.handler({"args": {**args, "squat_kg": 205}}, None)
    handler.handler({"args": {**args, "pk": "athlete-b"}}, None)
    identity[0] = "dataset-b"
    handler.handler({"args": args}, None)
    assert len(computed) == 5


def test_analysis_section_uses_supplied_snapshot(monkeypatch):
    core = importlib.import_module("services.handlers.analysis.analysis_section.core")
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
    analytics = importlib.import_module("services.handlers.analysis_reports.analytics")
    calculations = importlib.import_module("services.lib.lift_calculations")
    assert analytics.estimate_1rm(100, 5, 8) == calculations.estimate_1rm(100, 5, 8)
    assert analytics.calculate_dots(500, 80, "male") == calculations.calculate_dots(500, 80, "male")


def test_internal_e1rm_keeps_precision_before_regression():
    analytics = importlib.import_module("services.handlers.analysis_reports.analytics")
    calculations = importlib.import_module("services.lib.lift_calculations")
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
    monkeypatch.setenv("ANALYTICS_NODE_TOKEN", "loopback-secret")
    composite = importlib.import_module("services.handlers.analysis_reports.composite")
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
    monkeypatch.setenv("ANALYTICS_NODE_TOKEN", "loopback-secret")
    composite = importlib.import_module("services.handlers.analysis_reports.composite")
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"data": {"schemaVersion": 6}, "error": None}, request=httpx.Request("POST", url))

    monkeypatch.setattr(composite.httpx, "post", fake_post)
    composite.call_node("analytics.manifest", {"pk": "athlete-1", "_person_pk": "coach-1", "_if_job_id": "job-1", "_principal": "scope-token"})
    headers = calls[0][1]["headers"]
    assert headers["X-Person-Pk"] == "coach-1"
    assert headers["X-IF-Turn-Id"] == "job-1"
    assert headers["X-PL-Principal"] == "scope-token"
    assert headers["X-Internal-Token"] == "loopback-secret"
    assert calls[0][1]["json"] == {"pk": "athlete-1"}


def test_composite_block_cache_miss_preserves_not_found_status(monkeypatch):
    monkeypatch.setenv("ANALYTICS_NODE_TOKEN", "loopback-secret")
    composite = importlib.import_module("services.handlers.analysis_reports.composite")
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
    monkeypatch.setenv("ANALYTICS_NODE_TOKEN", "loopback-secret")
    composite = importlib.import_module("services.handlers.analysis_reports.composite")
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

    composite = importlib.import_module("services.handlers.analysis_reports.composite")
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
        "analytics.markdown": {"pk", "refresh", "cache_only"},
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
    export = importlib.import_module("services.handlers.analysis_reports.export")
    output = tmp_path / "program.md"
    export.build_program_markdown(
        {"meta": {"program_name": "Athlete A"}, "sessions": [], "phases": [], "goals": [], "competitions": []},
        str(output),
        analysis={"weekly": {}},
        export_context={"pk": "athlete-a"},
    )
    assert output.read_text(encoding="utf-8").startswith("# Athlete A")


def _markdown_sources(monkeypatch, core, program, glossary=None, glossary_reads=None):
    competition_entries = importlib.import_module("services.lib.competition_entries")
    valkey = importlib.import_module("services.lib.valkey")
    records = {}

    class Store:
        pk = "athlete-a"

        def invalidate_cache(self):
            return None

        async def get_program(self):
            return program

    class Glossary:
        async def get_glossary(self):
            if glossary_reads is not None:
                glossary_reads.append(True)
            return glossary or []

    monkeypatch.setattr(core, "_get_store", Store)
    monkeypatch.setattr(core, "_get_glossary_store", Glossary)
    monkeypatch.setattr(competition_entries, "with_competition_entries", lambda program, *_args: program)
    monkeypatch.setattr(valkey, "get_json", records.get)
    monkeypatch.setattr(valkey, "set_json", records.__setitem__)
    return records


def test_markdown_is_cached_until_an_analysis_input_write(monkeypatch):
    core = importlib.import_module("services.handlers.analysis_reports.core")
    renders = []
    program = {"meta": {"program_name": "Athlete A"}, "sessions": [], "phases": [], "goals": [], "competitions": []}
    records = _markdown_sources(monkeypatch, core, program)
    monkeypatch.setattr(core, "_build_sectioned_week_analysis", lambda *args, **kwargs: renders.append(True) or {})

    first = core.get_analysis_markdown({"pk": "athlete-a"})
    second = core.get_analysis_markdown({"pk": "athlete-a"})
    assert first["markdown"].startswith("# Athlete A") and first["cached"] is False
    assert second["markdown"] == first["markdown"] and second["cached"] is True
    assert len(renders) == 1 and len(records) == 1

    program["meta"]["program_name"] = "Athlete B"
    assert core.get_analysis_markdown({"pk": "athlete-a"})["markdown"] == first["markdown"]
    from services.analysis_version import record_write
    record_write("program_update_meta_field", "athlete-a")
    changed = core.get_analysis_markdown({"pk": "athlete-a"})
    assert changed["markdown"].startswith("# Athlete B") and changed["cached"] is False
    assert len(renders) == 2

    refreshed = core.get_analysis_markdown({"pk": "athlete-a", "refresh": True})
    assert refreshed["cached"] is False and len(renders) == 3


def test_markdown_cache_only_returns_a_miss_without_rendering(monkeypatch):
    core = importlib.import_module("services.handlers.analysis_reports.core")
    _markdown_sources(monkeypatch, core, {"meta": {}, "sessions": [], "competitions": []})
    monkeypatch.setattr(core, "_render_markdown", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cache-only rendered")))

    assert core.get_analysis_markdown({"pk": "athlete-a", "cache_only": True}) == {"cached": False, "cache_miss": True}


def test_markdown_dispatch_scopes_delegated_documents_and_rechecks_access(monkeypatch):
    core = importlib.import_module("services.handlers.analysis_reports.core")
    analysis_inputs = []
    glossary_reads = []
    program = {
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
    records = _markdown_sources(monkeypatch, core, program, [{"term": "private glossary"}], glossary_reads)

    def build_analysis(program, sessions, glossary, **kwargs):
        analysis_inputs.append((program, sessions, glossary))
        return {}

    monkeypatch.setattr(core, "_build_sectioned_week_analysis", build_analysis)

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

    read_access = {"is_self": False, "permissions": ["analytics:read", "sessions:read"]}
    cached = dispatch(operations["get_analysis_markdown"], {"pk": "athlete-a", "cache_only": True, "_access": read_access})
    assert cached["markdown"] == result["markdown"] and cached["cached"] is True

    for isolated in (
        {"is_self": False, "permissions": ["analytics:read"]},
        {"is_self": False, "permissions": ["analytics:read", "profile:read", "sessions:read"]},
    ):
        assert dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "cache_only": True, "_access": isolated}) == {"cached": False, "cache_miss": True}

    import pytest
    read_key = next(key for key in records if core._markdown_cache_key({"_access": read_access}) in key)
    records[read_key] = {**records[read_key], "access_requirements": {"permissions": ["sessions:read", "goals:read"], "competition_ids": []}}
    with pytest.raises(Exception, match="Access to this saved result has changed"):
        dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "cache_only": True, "_access": read_access})


def test_markdown_athlete_reads_never_share_delegate_records(monkeypatch):
    core = importlib.import_module("services.handlers.analysis_reports.core")
    _markdown_sources(monkeypatch, core, {"meta": {"program_name": "Mine"}, "sessions": [], "phases": [], "goals": [], "competitions": []})
    monkeypatch.setattr(core, "_build_sectioned_week_analysis", lambda *args, **kwargs: {})
    operations = load_operations("analytics")
    dispatch(operations["analytics.markdown"], {"pk": "athlete-a", "_access": {"is_self": False, "permissions": ["analytics:write", "sessions:read"]}})
    assert dispatch(operations["get_analysis_markdown"], {"pk": "athlete-a", "cache_only": True, "_access": {"is_self": True}}) == {"cached": False, "cache_miss": True}
    dispatch(operations["get_analysis_markdown"], {"pk": "athlete-a", "_access": {"is_self": True}})
    for name in ("analytics.markdown", "get_analysis_markdown"):
        result = dispatch(operations[name], {"pk": "athlete-a", "cache_only": True, "_access": {"is_self": True}})
        assert result["markdown"].startswith("# Mine") and result["cached"] is True



def test_overview_reports_why_upcoming_competitions_could_not_be_projected(monkeypatch):
    import importlib

    analytics = importlib.import_module("services.handlers.analysis_reports.analytics")
    monkeypatch.setattr(analytics, "meet_projection", lambda *args, **kwargs: {"status": "insufficient_data", "reason": "No session data to estimate maxes from"})
    program = {
        "meta": {"program_start": "2026-10-06"},
        "competitions": [{"name": "Royal City Rumble 5", "date": "2027-05-01", "status": "confirmed"}],
        "sessions": [],
    }
    result = analytics.weekly_analysis_section(
        program, [], "overview",
        window_start="2026-10-06", window_end="2026-10-31", ref_date="2026-10-31",
        week_start=1, week_end=4, weeks=4, block="current",
    )
    assert result["projections"] == []
    assert result["projection_reason"] == "No session data to estimate maxes from"

