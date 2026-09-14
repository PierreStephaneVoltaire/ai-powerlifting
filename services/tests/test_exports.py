import base64
import importlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

from services.contract import load_operations


class Store:
    def __init__(self, pk):
        self.pk = pk

    async def get_program(self):
        return {"pk": self.pk, "sessions": []}


def test_history_exports_are_scoped_and_isolated(monkeypatch):
    core = importlib.import_module("lambda.pod_training_program.handlers.export_program_history.core")
    directories = []

    def write(program, sessions, store, directory, format_value):
        directories.append(directory)
        filename = f"{store.pk}.{format_value}.bin"
        Path(directory, filename).write_bytes(store.pk.encode())
        return filename, "export", "markdown" if format_value == "markdown" else "xlsx"

    monkeypatch.setattr(core, "_get_store", lambda args: Store(args["pk"]))
    monkeypatch.setattr(core, "_write_program_export", write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pk: core.export_program_history({"pk": pk, "format": "xlsx"}), ("athlete-a", "athlete-b")))

    assert {base64.b64decode(result["content_base64"]).decode() for result in results} == {"athlete-a", "athlete-b"}
    assert len(set(directories)) == 2
    load_operations("program")["export_program_history"].validate_result(results[0])


def test_markdown_export_uses_the_callers_athlete_and_private_tempfile(monkeypatch):
    core = importlib.import_module("lambda.pod_training_program.handlers.export_program_markdown.core")
    module_name = "lambda.pod_training_program.handlers.export_program_markdown.export"
    fake_export = ModuleType(module_name)

    def build(program, path, **_kwargs):
        Path(path).write_text(program["pk"], encoding="utf-8")

    fake_export.build_program_markdown = build
    monkeypatch.setattr(core, "_get_store", lambda args: Store(args["pk"]))
    monkeypatch.setattr(core, "_build_analysis_bundle", lambda *_args: {})
    monkeypatch.setattr(core, "_scope_program_to_current_block", lambda program: program)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, module_name, fake_export)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pk: core.export_program_markdown({"pk": pk}), ("athlete-a", "athlete-b")))

    assert {result["markdown"] for result in results} == {"athlete-a", "athlete-b"}
