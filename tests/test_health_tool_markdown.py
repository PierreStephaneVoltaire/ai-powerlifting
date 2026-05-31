import importlib
import sys
import types
from pathlib import Path


def _module(name, **attrs):
    module = types.ModuleType(name)
    for attr_name, value in attrs.items():
        setattr(module, attr_name, value)
    return module


def test_get_analysis_markdown_logs_cache_failure_and_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("IF_MCP_ALLOWED_TOOLS", "1")
    monkeypatch.setitem(
        sys.modules,
        "pydantic",
        _module("pydantic", Field=lambda default=None, **kwargs: default),
    )

    class SdkBase:
        def __init__(self, *args, **kwargs):
            pass

        @classmethod
        def __class_getitem__(cls, item):
            return cls

        @classmethod
        def from_text(cls, text):
            return cls()

    monkeypatch.setitem(
        sys.modules,
        "tools.sdk_compat",
        _module(
            "tools.sdk_compat",
            Action=SdkBase,
            Observation=SdkBase,
            Tool=SdkBase,
            ToolDefinition=SdkBase,
            ToolExecutor=SdkBase,
            register_tool=lambda *args, **kwargs: None,
        ),
    )

    health_tool = importlib.import_module("tools.health.tool")

    class FakeStore:
        pk = "test"

        def __init__(self):
            self.invalidated = False

        def invalidate_cache(self):
            self.invalidated = True

        async def get_program(self):
            return {
                "meta": {"sex": "male"},
                "sessions": [
                    {
                        "date": "2026-05-30",
                        "block": "current",
                        "week_number": 1,
                    }
                ],
            }

    class FakeGlossaryStore:
        async def get_glossary(self):
            return []

    class FakeAnalysisCacheStore:
        def __init__(self, **kwargs):
            pass

        def get_markdown_cache(self, key):
            raise RuntimeError("cache unavailable")

    class FakeTable:
        def put_item(self, Item):
            self.item = Item

    fake_table = FakeTable()
    fake_store = FakeStore()

    def build_program_markdown(program, out_path, analysis=None, export_context=None):
        Path(out_path).write_text("# fallback markdown\n", encoding="utf-8")

    caplog.set_level("WARNING", logger=health_tool.__name__)
    monkeypatch.setattr(
        health_tool,
        "_build_sectioned_week_analysis",
        lambda *args, **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        health_tool,
        "_scope_program_to_current_block",
        lambda program: program,
    )
    monkeypatch.setitem(
        sys.modules,
        "core",
        _module(
            "core",
            _get_store=lambda: fake_store,
            _floats_to_decimals=lambda item: item,
            _get_glossary_store=lambda: FakeGlossaryStore(),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "export",
        _module("export", build_program_markdown=build_program_markdown),
    )
    monkeypatch.setitem(
        sys.modules,
        "config",
        _module("config", ANALYSIS_CACHE_TABLE_NAME="analysis-cache", AWS_REGION="us-east-1"),
    )
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        _module(
            "boto3",
            resource=lambda service, region_name=None: types.SimpleNamespace(
                Table=lambda table_name: fake_table
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "analysis_cache",
        _module("analysis_cache", AnalysisCacheStore=FakeAnalysisCacheStore),
    )

    result = health_tool._do_get_analysis_markdown({"max_age_hours": 72})

    assert result["markdown"] == "# fallback markdown\n"
    assert result["cached"] is False
    assert fake_store.invalidated is True
    assert any(
        "get_analysis_markdown cache path failed" in record.message
        for record in caplog.records
    )
