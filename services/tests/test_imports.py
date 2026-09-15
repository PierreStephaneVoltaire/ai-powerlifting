import base64
import asyncio
import importlib

import pytest

from services.contract import load_operations
from services.dispatch import dispatch


class FakeImportStore:
    def __init__(self, pending=None, imports=None):
        self.pending = pending
        self.imports = imports or []
        self.applied = []
        self.rejected = []
        self.staged = []

    async def get_pending(self, import_id):
        return self.pending if self.pending and self.pending.get("import_id") == import_id else None

    async def list_pending(self, import_type=None):
        return [item for item in self.imports if item.get("status") == "awaiting_review" and (not import_type or item.get("import_type") == import_type)]

    async def list_imports(self):
        return self.imports

    async def stage_import(self, record):
        self.staged.append(record)
        return "import-new"

    async def claim_apply(self, import_id, claim_id, at):
        if self.pending.get("status") != "awaiting_review":
            raise RuntimeError("conditional claim failed")
        self.pending["status"] = "applying"
        self.pending["apply_claim_id"] = claim_id
        return self.pending

    async def mark_applied(self, import_id, at, claim_id):
        self.pending["status"] = "applied"
        self.applied.append((import_id, at))

    async def mark_uncertain(self, import_id, claim_id, reason):
        self.pending["status"] = "uncertain"
        self.pending["uncertainty_reason"] = reason

    async def mark_rejected(self, import_id, reason=None):
        self.rejected.append((import_id, reason))


class FakeProgramStore:
    def __init__(self, program):
        self.program = program
        self.saved = None

    async def get_program(self):
        return self.program

    async def _write_new_version(self, program, minor=False):
        self.saved = program
        program.setdefault("meta", {})["version_label"] = "2.0"
        return program


class FailingProgramStore(FakeProgramStore):
    async def _write_new_version(self, program, minor=False):
        self.saved = program
        raise RuntimeError("target write failed after mutation")


class FakeTemplateStore:
    def __init__(self):
        self.template = None
        self.kwargs = None

    async def put_template(self, template, **kwargs):
        self.template = template
        self.kwargs = kwargs
        return "template#new"


def test_import_inventory_has_precise_shapes_and_replacement_handlers():
    operations = load_operations("imports")
    assert len(operations) == 6
    assert all("pod_imports" in operation.handler for operation in operations.values())
    with pytest.raises(Exception):
        operations["import_apply"].validate_input({"import_id": "x", "merge_strategy": "bogus", "pk": "athlete-1"})
    operations["import_apply"].validate_result({"status": "applied", "applied_count": 1, "skipped_count": 0, "new_version": "2.0"})


def test_parse_stages_csv_using_authenticated_scope_and_native_parser(monkeypatch):
    core = importlib.import_module("lambda.pod_imports.handlers.import_parse_file.core")
    ai = importlib.import_module("lambda.pod_imports.handlers.import_parse_file.import_parse_ai")
    imports = FakeImportStore()

    class Glossary:
        async def get_glossary(self):
            return []

        async def fuzzy_resolve(self, name, threshold):
            return "glossary#squat" if name == "Squat" else None

    async def parse(*args):
        return {"phases": [], "sessions": [{"date": "2026-09-15", "exercises": [{"name": "Squat"}]}], "warnings": [], "parse_notes": "ok"}

    monkeypatch.setattr(core, "_get_program_store", lambda pk: FakeProgramStore({"current_maxes": {}, "sessions": []}))
    monkeypatch.setattr(core, "_get_glossary_store", lambda pk: Glossary())
    monkeypatch.setattr(core, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(ai, "generate_import_parse_report", parse)
    result = dispatch(load_operations("imports")["import_parse_file"], {"pk": "athlete-1", "base64_content": base64.b64encode(b"date,exercise\n2026-09-15,Squat\n").decode(), "filename": "sessions.csv"})

    assert result == {"import_id": "import-new", "classification": "session_import", "warnings": [], "parse_notes": "ok"}
    assert imports.staged[0]["source_filename"] == "sessions.csv"
    assert imports.staged[0]["ai_parse_result"]["sessions"][0]["exercises"][0]["glossary_id"] == "glossary#squat"


def test_apply_session_offsets_dates_and_preserves_program_write(monkeypatch):
    apply = importlib.import_module("lambda.pod_imports.handlers.import_apply.core")
    imports = FakeImportStore({"import_id": "import-1", "status": "awaiting_review", "import_type": "session_import", "ai_parse_result": {"sessions": [{"date": "2026-09-01", "exercises": [{"name": "Squat"}]}]}})
    program = FakeProgramStore({"meta": {"version_label": "1.0"}, "sessions": [{"date": "2026-09-10", "exercises": []}]})
    monkeypatch.setattr(apply, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(apply, "_get_program_store", lambda pk: program)

    result = asyncio.run(apply.import_apply({"pk": "athlete-1", "import_id": "import-1", "start_date": "2026-09-20", "merge_strategy": "append"}))

    assert result == {"status": "applied", "applied_count": 1, "skipped_count": 0, "new_version": "2.0"}
    assert program.saved["sessions"][1]["date"] == "2026-09-20"
    assert imports.applied


def test_apply_template_writes_owned_template_with_import_lineage(monkeypatch):
    apply = importlib.import_module("lambda.pod_imports.handlers.import_apply.core")
    imports = FakeImportStore({"import_id": "import-2", "status": "awaiting_review", "import_type": "template", "source_filename": "block.csv", "source_file_hash": "sha256:abc", "ai_parse_result": {"phases": [], "sessions": [{"week_number": 1, "day_index": 1, "exercises": [{"name": "Squat", "load_type": "percentage", "load_value": 75}]}], "parse_notes": "parsed"}})
    templates = FakeTemplateStore()
    monkeypatch.setattr(apply, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(apply, "_get_template_store", lambda: templates)

    with pytest.raises(ValueError, match='Verified acting Person'):
        asyncio.run(apply.import_apply({'pk': 'athlete-1', 'import_id': 'import-2', 'actor_pk': 'forged'}))
    assert imports.pending['status'] == 'awaiting_review'
    result = asyncio.run(apply.import_apply({"pk": "athlete-1", "_person_pk": "coach-person", "import_id": "import-2", "author": "Ari"}))

    assert result == {"status": "applied", "target_sk": "template#new"}
    assert templates.kwargs == {"actor_pk": "coach-person", "author": "Ari", "published": False, "import_job_id": "import-2"}
    assert templates.template["sessions"][0]["exercises"][0]["load_value"] == 0.75


def test_failed_target_write_marks_import_uncertain_and_blocks_replay(monkeypatch):
    apply = importlib.import_module("lambda.pod_imports.handlers.import_apply.core")
    imports = FakeImportStore({"import_id": "import-3", "status": "awaiting_review", "import_type": "session_import", "ai_parse_result": {"sessions": [{"date": "2026-09-01", "exercises": [{"name": "Squat"}]}]}})
    program = FailingProgramStore({"meta": {"version_label": "1.0"}, "sessions": []})
    monkeypatch.setattr(apply, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(apply, "_get_program_store", lambda pk: program)

    with pytest.raises(RuntimeError, match="target write failed"):
        asyncio.run(apply.import_apply({"pk": "athlete-1", "import_id": "import-3"}))
    assert imports.pending["status"] == "uncertain"
    assert len(program.saved["sessions"]) == 1
    with pytest.raises(ValueError, match="do not replay"):
        asyncio.run(apply.import_apply({"pk": "athlete-1", "import_id": "import-3"}))
    assert len(program.saved["sessions"]) == 1
