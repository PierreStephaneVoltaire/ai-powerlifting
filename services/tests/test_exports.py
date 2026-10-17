import base64
import importlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

from services.contract import load_operations
from services.dispatch import dispatch
from services.lib import competition_entries


class Store:
    def __init__(self, pk):
        self.pk = pk

    async def get_program(self):
        return {"pk": self.pk, "sessions": []}


def test_history_exports_are_scoped_and_isolated(monkeypatch):
    core = importlib.import_module("services.handlers.program.export_program_history.core")
    directories = []

    def write(program, session_block, window, store, directory, format_value):
        directories.append(directory)
        filename = f"{store.pk}.{format_value}.bin"
        Path(directory, filename).write_bytes(store.pk.encode())
        return filename, "export", "markdown" if format_value == "markdown" else "xlsx"

    monkeypatch.setattr(core, "_get_store", lambda args: Store(args["pk"]))
    monkeypatch.setattr(competition_entries, "load_entries", lambda pk, *_args, **_kwargs: [])
    monkeypatch.setattr(core, "_write_program_export", write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pk: core.export_program_history({"pk": pk, "format": "xlsx"}), ("athlete-a", "athlete-b")))

    assert {base64.b64decode(result["content_base64"]).decode() for result in results} == {"athlete-a", "athlete-b"}
    assert len(set(directories)) == 2
    load_operations("export")["export_program_history"].validate_result(results[0])


def test_markdown_export_uses_the_callers_athlete_and_private_tempfile(monkeypatch):
    core = importlib.import_module("services.handlers.program.export_program_markdown.core")
    module_name = "services.handlers.program.export_program_markdown.export"
    fake_export = ModuleType(module_name)

    def build(program, path, **_kwargs):
        Path(path).write_text(program["pk"], encoding="utf-8")

    fake_export.build_program_markdown = build
    monkeypatch.setattr(core, "_get_store", lambda args: Store(args["pk"]))
    monkeypatch.setattr(competition_entries, "load_entries", lambda pk, *_args, **_kwargs: [])
    monkeypatch.setattr(core, "_build_analysis_bundle", lambda *_args: {})
    monkeypatch.setattr(core, "_scope_program_to_current_block", lambda program: program)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, module_name, fake_export)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pk: core.export_program_markdown({"pk": pk}), ("athlete-a", "athlete-b")))

    assert {result["markdown"] for result in results} == {"athlete-a", "athlete-b"}


def test_export_dispatch_includes_only_permitted_independent_entries(monkeypatch):
    core = importlib.import_module("services.handlers.program.export_program_history.core")
    monkeypatch.setattr(core, "_get_store", lambda args: Store(args["pk"]))
    monkeypatch.setattr(competition_entries, "load_entries", lambda pk, *_args, **_kwargs: [
        {"master_id": "tied", "name": "Visible meet", "user_status": "completed", "start_date": "2026-09-01", "block_id": "current", "results": {"squat_kg": 180}},
        {"master_id": "private", "name": "Hidden meet", "user_status": "completed", "start_date": "2026-08-01", "block_id": "current", "results": {"squat_kg": 170}},
    ])
    def write(program, session_block, window, store, directory, format_value):
        assert [entry["master_id"] for entry in program["competitions"]] == ["tied"]
        assert program["competitions"][0]["results"]["squat_kg"] == 180
        Path(directory, "history.md").write_text(program["competitions"][0]["name"])
        return "history.md", "export", "markdown"
    monkeypatch.setattr(core, "_write_program_export", write)
    access = {"permissions": ["program:read", "competition:read"], "competition_scope": {"read": ["tied"]}}
    result = dispatch(load_operations("export")["export_program_history"], {"pk": "athlete", "format": "markdown", "_access": access})
    assert base64.b64decode(result["content_base64"]) == b"Visible meet"


class TwoBlockStore(Store):
    async def get_program(self):
        return {
            "pk": self.pk,
            "phases": [],
            "sessions": [
                {"date": "2025-01-06", "week_number": 1, "block": "block-2025", "block_id": "block-2025", "completed": True},
                {"date": "2025-01-13", "week_number": 2, "block": "block-2025", "block_id": "block-2025", "completed": True},
                {"date": "2026-10-05", "week_number": 1, "block": "current", "block_id": "block-new", "completed": True},
                {"date": "2026-10-12", "week_number": 2, "block": "current", "block_id": "block-new", "completed": True},
            ],
            "diet_notes": [{"date": "2025-01-07", "notes": "old", "block_id": "block-2025"}, {"date": "2026-10-06", "notes": "new", "block_id": "block-new"}],
            "supplements": [{"name": "old-creatine", "dose": "5g", "block_id": "block-2025"}, {"name": "current-creatine", "dose": "5g"}],
            "supplement_phases": [{"phase": 1, "block_id": "block-2025"}, {"phase": 2, "block_id": "block-new"}],
            "competitions": [{"name": "old", "date": "2026-08-22", "block_id": "block-2025"}, {"name": "new", "date": "2026-11-07"}],
            "meta": {"current_block_id": "block-new", "program_start": "2025-01-01", "comp_date": "2026-08-22", "blocks": [{"id": "block-2025", "status": "completed", "start_date": "2025-01-01", "completed_at": "2026-10-05"}, {"id": "block-new", "status": "active", "start_date": "2026-10-06"}], "block_notes": [{"date": "2026-05-01", "notes": "old"}, {"date": "2026-10-06", "notes": "new", "block_id": "block-new"}]},
        }


def _capture_export(monkeypatch, args):
    core = importlib.import_module("services.handlers.program.export_program_history.core")
    captured = {}

    def write(program, session_block, window, store, directory, format_value):
        captured.update(program=program, session_block=session_block, window=window)
        Path(directory, "out.md").write_text("x")
        return "out.md", "export", "markdown"

    monkeypatch.setattr(core, "_get_store", lambda a: TwoBlockStore(a["pk"]))
    monkeypatch.setattr(competition_entries, "load_entries", lambda pk, *_args, **_kwargs: [])
    monkeypatch.setattr(core, "_write_program_export", write)
    core.export_program_history({"pk": "athlete", "format": "markdown", **args})
    return captured


def test_export_defaults_to_active_block_only(monkeypatch):
    captured = _capture_export(monkeypatch, {})
    assert [s["date"] for s in captured["program"]["sessions"]] == ["2026-10-05", "2026-10-12"]
    assert [n["notes"] for n in captured["program"]["diet_notes"]] == ["new"]
    assert [item["name"] for item in captured["program"]["supplements"]] == ["current-creatine"]
    assert [item["name"] for item in captured["program"]["competitions"]] == ["new"]
    assert [item["notes"] for item in captured["program"]["meta"]["block_notes"]] == ["new"]
    assert [item["phase"] for item in captured["program"]["supplement_phases"]] == [2]
    assert captured["program"]["meta"]["comp_date"] == "2026-11-07"
    assert captured["session_block"] == "current"


def test_export_follows_selected_window(monkeypatch):
    captured = _capture_export(monkeypatch, {"block": "current", "week_start": "2", "week_end": "2", "window_start": "2026-10-12", "window_end": "2026-10-18"})
    assert [s["date"] for s in captured["program"]["sessions"]] == ["2026-10-12"]
    assert captured["window"]["week_start"] == 2


def test_export_of_past_block_excludes_active_block(monkeypatch):
    captured = _capture_export(monkeypatch, {"block": "block-2025"})
    assert [s["date"] for s in captured["program"]["sessions"]] == ["2025-01-06", "2025-01-13"]
    assert captured["session_block"] == "block-2025"
