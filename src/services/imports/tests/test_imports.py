import base64
import asyncio
import importlib
import io

import pytest

from services.runtime.contract import load_operations
from services.runtime.dispatch import dispatch


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
    assert all("services.imports" in operation.handler for operation in operations.values())
    with pytest.raises(Exception):
        operations["import_apply"].validate_input({"import_id": "x", "merge_strategy": "bogus", "pk": "athlete-1"})
    operations["import_apply"].validate_result({"status": "applied", "applied_count": 1, "skipped_count": 0, "new_version": "2.0"})


def test_parse_stages_csv_using_authenticated_scope_and_native_parser(monkeypatch):
    core = importlib.import_module("services.imports.import_parse_file.core")
    ai = importlib.import_module("services.imports.import_parse_file.import_parse_ai")
    imports = FakeImportStore()

    class Glossary:
        async def get_glossary(self):
            return []

        async def fuzzy_resolve(self, name, threshold, exercises=None):
            return "glossary#squat" if name == "Squat" else None

    async def parse(*args):
        return {"phases": [], "sessions": [{"date": "2026-09-15", "exercises": [{"name": "Squat"}]}], "warnings": [], "parse_notes": "ok"}

    monkeypatch.setattr(core, "_get_program_store", lambda pk: FakeProgramStore({"current_maxes": {}, "sessions": []}))
    monkeypatch.setattr(core, "_get_glossary_store", lambda pk: Glossary())
    monkeypatch.setattr(core, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(ai, "generate_import_parse_report", parse)
    result = dispatch(load_operations("imports")["import_parse_file"], {"pk": "athlete-1", "base64_content": base64.b64encode(b"date,exercise\n2026-09-15,Squat\n").decode(), "filename": "sessions.csv", "import_type": "session_import"})

    assert result == {"import_id": "import-new", "classification": "session_import", "warnings": [], "parse_notes": "ok"}
    assert imports.staged[0]["source_filename"] == "sessions.csv"
    assert imports.staged[0]["ai_parse_result"]["sessions"][0]["exercises"][0]["glossary_id"] == "glossary#squat"


def test_template_parser_receives_workbook_title_and_import_instructions(monkeypatch):
    from openpyxl import Workbook
    from services.imports.import_parse_file import core, import_parse_ai

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Week 1"
    sheet.append(["Candito 6 Week Powerlifting Program"])
    sheet.append(["Day", "Exercise"])
    sheet.append(["Monday", "Squat"])
    content = io.BytesIO()
    workbook.save(content)
    imports = FakeImportStore()

    class Glossary:
        async def get_glossary(self):
            return []

        async def fuzzy_resolve(self, *args, **kwargs):
            return None

    async def parse(rows, filename, classification, context, instructions, sheet_headings):
        assert filename == "program.xlsx"
        assert classification == "template"
        assert instructions == "Name this Candito Meet Prep"
        assert "Candito 6 Week Powerlifting Program" in sheet_headings["Week 1"]
        return {"program_name": "Candito Meet Prep", "sessions": [{"exercises": [{"name": "Squat"}]}]}

    monkeypatch.setattr(core, "_get_glossary_store", lambda pk: Glossary())
    monkeypatch.setattr(core, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(import_parse_ai, "generate_import_parse_report", parse)
    dispatch(load_operations("imports")["import_parse_file"], {
        "pk": "athlete-1", "filename": "program.xlsx", "import_type": "template",
        "base64_content": base64.b64encode(content.getvalue()).decode(),
        "import_instructions": "Name this Candito Meet Prep",
    })

    assert imports.staged[0]["ai_parse_result"]["program_name"] == "Candito Meet Prep"


def test_apply_session_offsets_dates_and_preserves_program_write(monkeypatch):
    apply = importlib.import_module("services.imports.import_apply.core")
    imports = FakeImportStore({"import_id": "import-1", "status": "awaiting_review", "import_type": "session_import", "ai_parse_result": {"sessions": [{"date": "2026-09-01", "exercises": [{"name": "Squat"}]}]}})
    program = FakeProgramStore({"meta": {"version_label": "1.0"}, "sessions": [{"date": "2026-09-10", "exercises": []}]})
    monkeypatch.setattr(apply, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(apply, "_get_program_store", lambda pk: program)

    result = asyncio.run(apply.import_apply({"pk": "athlete-1", "import_id": "import-1", "start_date": "2026-09-20", "merge_strategy": "append"}))

    assert result == {"status": "applied", "applied_count": 1, "skipped_count": 0, "new_version": "2.0"}
    assert program.saved["sessions"][1]["date"] == "2026-09-20"
    assert imports.applied


@pytest.mark.parametrize(("parsed_name", "source_filename", "expected_name"), [
    ("Candito 6 Week", "block.csv", "Candito 6 Week"),
    ("Imported Template", "block.csv", "block"),
    (None, "block.csv", "block"),
    (None, "Imported_Template.csv", "1-Week Training Program"),
])
def test_apply_template_writes_owned_template_with_import_lineage(monkeypatch, parsed_name, source_filename, expected_name):
    apply = importlib.import_module("services.imports.import_apply.core")
    imports = FakeImportStore({"import_id": "import-2", "status": "awaiting_review", "import_type": "template", "source_filename": "block.csv", "source_file_hash": "sha256:abc", "ai_parse_result": {"phases": [], "sessions": [{"week_number": 1, "day_index": 1, "exercises": [{"name": "Squat", "load_type": "percentage", "load_value": 75}]}], "parse_notes": "parsed"}})
    templates = FakeTemplateStore()
    imports.pending["ai_parse_result"]["program_name"] = parsed_name
    imports.pending["source_filename"] = source_filename
    monkeypatch.setattr(apply, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(apply, "_get_template_store", lambda: templates)

    with pytest.raises(ValueError, match='Verified acting Person'):
        asyncio.run(apply.import_apply({'pk': 'athlete-1', 'import_id': 'import-2', 'actor_pk': 'forged'}))
    assert imports.pending['status'] == 'awaiting_review'
    result = asyncio.run(apply.import_apply({"pk": "athlete-1", "_person_pk": "coach-person", "import_id": "import-2", "author": "Ari"}))

    assert result == {"status": "applied", "target_sk": "template#new"}
    assert templates.kwargs == {"actor_pk": "coach-person", "author": "Ari", "published": False, "import_job_id": "import-2"}
    assert templates.template["meta"]["name"] == expected_name
    assert templates.template["sessions"][0]["exercises"][0]["load_value"] == 0.75


def test_failed_target_write_marks_import_uncertain_and_blocks_replay(monkeypatch):
    apply = importlib.import_module("services.imports.import_apply.core")
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


def test_apply_template_defaults_unloaded_exercises_to_rpe_8_drops_dates_and_links_main_lifts(monkeypatch):
    apply = importlib.import_module("services.imports.import_apply.core")
    sessions = [{"week_number": 1, "day_of_week": "Saturday", "date": "2027-01-02", "exercises": [
        {"name": "Squat heavy single", "sets": 1, "reps": 1, "load_type": "absolute", "load_value": 162.5},
        {"name": "Weighted pull-up", "sets": 2, "reps": 8, "load_type": "unresolvable", "load_value": None, "notes": "add 5 lb per week"},
        {"name": "Dead bug", "sets": 1, "reps": 8},
        {"name": "Pause bench", "sets": 2, "reps": 4, "load_type": "absolute", "load_value": 105},
    ]}]
    imports = FakeImportStore({"import_id": "import-3", "status": "awaiting_review", "import_type": "session_import", "source_filename": "peak.xlsx", "source_file_hash": "sha256:def", "ai_parse_result": {"phases": [], "sessions": sessions, "parse_notes": "parsed"}})
    templates = FakeTemplateStore()
    monkeypatch.setattr(apply, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(apply, "_get_template_store", lambda: templates)
    monkeypatch.setattr(apply, "_glossary", lambda pk: [{"id": "g-squat", "name": "Squat"}, {"id": "g-bench", "name": "Bench Press"}])

    asyncio.run(apply.import_apply({"pk": "athlete-1", "_person_pk": "coach-person", "import_id": "import-3", "classification_override": "template"}))

    session = templates.template["sessions"][0]
    squat, pullup, deadbug, pause = session["exercises"]
    assert "date" not in session
    assert squat["glossary_id"] == "g-squat" and squat["load_value"] == 162.5
    assert (pullup["load_type"], pullup["load_value"], pullup["rpe_target"]) == ("rpe", 8, 8)
    assert pullup["notes"] == "add 5 lb per week"
    assert (deadbug["load_type"], deadbug["load_value"]) == ("rpe", 8)
    assert deadbug["notes"] == ""
    assert squat["notes"] == ""
    assert "glossary_id" not in pause or pause["glossary_id"] is None


def test_template_import_preserves_amrap_and_timed_exercises():
    from services.imports.import_apply.core import _prepare_template

    result = _prepare_template({"sessions": [{"week_number": 1, "exercises": [
        {"name": "Leg Curl", "sets": 2, "reps": None, "rep_mode": "amrap"},
        {"name": "Air Bike", "sets": 1, "reps": 15, "rep_unit": "minutes"},
        {"name": "Plank", "sets": 2, "reps": 30, "rep_unit": "seconds", "load_type": "rpe", "load_value": 6.5},
        {"name": "Rear Delt Fly", "sets": 3, "reps": 10, "load_type": "rpe", "load_value": 7.5},
        {"name": "Cable Row", "sets": 3, "reps": 8},
    ]}]})
    leg_curl, bike, plank, fly, row = result["sessions"][0]["exercises"]
    assert leg_curl["rep_mode"] == "amrap"
    assert (leg_curl["load_type"], leg_curl["load_value"]) == ("rpe", 8)
    assert (bike["reps"], bike["rep_unit"]) == (15, "minutes")
    assert bike["sets"] == 1
    assert bike["load_type"] == "duration"
    assert bike.get("rpe_target") is None
    assert (plank["reps"], plank["rep_unit"], plank["load_type"], plank["load_value"]) == (30, "seconds", "rpe", 6.5)
    assert plank["rpe_target"] == 6.5
    assert fly["rpe_target"] == 7.5
    assert (row["load_type"], row["load_value"], row["rpe_target"]) == ("rpe", 8, 8)


def test_template_import_validates_ai_glossary_ids(monkeypatch):
    from services.imports.import_parse_file import core, import_parse_ai

    imports = FakeImportStore()

    class Glossary:
        async def get_glossary(self):
            return [{"id": "back", "name": "Back Extension"}, {"id": "curl", "name": "Leg Curl"}]

        async def fuzzy_resolve(self, name, **kwargs):
            return "curl" if name == "Leg Curls" else None

    async def parse(rows, filename, classification, context, instructions, headings):
        assert context["glossary"] == await Glossary().get_glossary()
        return {"sessions": [{"exercises": [
            {"name": "45° Back Extension", "glossary_id": "back"},
            {"name": "Unknown", "glossary_id": "invented"},
            {"name": "Back Extension", "glossary_id": "curl"},
            {"name": "Leg Curls"},
        ]}]}

    monkeypatch.setattr(core, "_get_glossary_store", lambda pk: Glossary())
    monkeypatch.setattr(core, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(import_parse_ai, "generate_import_parse_report", parse)
    dispatch(load_operations("imports")["import_parse_file"], {
        "pk": "athlete-1", "filename": "program.csv", "import_type": "template",
        "base64_content": base64.b64encode(b"day,exercise\nMonday,example\n").decode(),
    })
    first, second, exact, fuzzy = imports.staged[0]["ai_parse_result"]["sessions"][0]["exercises"]
    assert (first["name"], first["glossary_id"]) == ("Back Extension", "back")
    assert "glossary_id" not in second
    assert (exact["name"], exact["glossary_id"]) == ("Back Extension", "back")
    assert (fuzzy["name"], fuzzy["glossary_id"]) == ("Leg Curl", "curl")
    assert fuzzy["notes"] == ""


@pytest.mark.parametrize(("headers", "rows", "expected"), [
    (b"WEEK,DAY,EXERCISE,EXERCISE NOTES\n1,Monday,Squat,Keep knees out\n1,Tuesday,Squat,Brace hard\n",
     [{"week_number": 1, "day_of_week": "Monday", "exercises": [{"name": "Squat", "notes": "Keep knees out"}]},
      {"week_number": 1, "day_of_week": "Tuesday", "exercises": [{"name": "Squat", "notes": "Brace hard"}]}],
     ["Keep knees out", "Brace hard"]),
    (b"day,exercise,notes\nMonday,Squat,One note\nTuesday,Squat,Another note\n",
     [{"week_number": 1, "day_of_week": "Monday", "exercises": [{"name": "Squat", "notes": "One note"}]},
      {"week_number": 1, "day_of_week": "Tuesday", "exercises": [{"name": "Squat", "notes": "Another note"}]}],
     ["One note", "Another note"]),
])
def test_import_notes_only_copies_exact_text_from_an_exercise_notes_column(monkeypatch, headers, rows, expected):
    from services.imports.import_parse_file import core, import_parse_ai

    imports = FakeImportStore()

    class Glossary:
        async def get_glossary(self):
            return []

        async def fuzzy_resolve(self, *args, **kwargs):
            return None

    async def parse(*args):
        return {"sessions": rows}

    monkeypatch.setattr(core, "_get_glossary_store", lambda pk: Glossary())
    monkeypatch.setattr(core, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(import_parse_ai, "generate_import_parse_report", parse)
    dispatch(load_operations("imports")["import_parse_file"], {
        "pk": "athlete-1", "filename": "program.csv", "import_type": "template",
        "base64_content": base64.b64encode(
            headers
        ).decode(),
    })

    parsed_sessions = imports.staged[0]["ai_parse_result"]["sessions"]
    assert [session["exercises"][0]["notes"] for session in parsed_sessions] == expected


@pytest.mark.parametrize("context", [{}, {"Week": 1}])
def test_import_notes_are_cleared_when_repeated_exercise_occurrence_is_ambiguous(context):
    from services.imports.import_parse_file.core import _normalize_exercise_names, _source_exercise_notes

    source = _source_exercise_notes([{"Exercise": "Squat", "Notes": "Brace hard", **context}])
    parsed = {"sessions": [
        {"week_number": 1, "day_of_week": "Monday", "exercises": [{"name": "Squat", "notes": "Brace hard"}]},
        {"week_number": 1, "day_of_week": "Tuesday", "exercises": [{"name": "Squat", "notes": "Brace hard"}]},
    ]}
    _normalize_exercise_names(parsed, source)
    assert [session["exercises"][0]["notes"] for session in parsed["sessions"]] == ["", ""]


def test_new_exercises_require_complete_profiles_and_reuse_existing(monkeypatch):
    from services.imports.import_parse_file.glossary import create_missing_exercises

    calls = []
    monkeypatch.setattr("services.runtime.analytics_client.call", lambda operation, arguments, **kwargs: calls.append(arguments) or {"id": arguments["exercise"]["id"]})
    profile = {"axial": 0.1, "neural": 0.2, "peripheral": 0.3, "systemic": 0.4}
    proposed = [{"name": "Cable Oblique Crunch", "category": "core", "fatigue_category": "accessory", "equipment": "cable",
                 "primary_muscles": ["obliques"], "secondary_muscles": ["core"], "tertiary_muscles": [],
                 "fatigue_profile": profile, "fatigue_profile_reasoning": "Cable isolation."}]
    result = create_missing_exercises({"Cable Oblique Crunch"}, proposed, [], "athlete-1")
    assert result["Cable Oblique Crunch"]
    assert calls[0]["exercise"]["fatigue_profile_source"] == "ai_estimated"
    assert create_missing_exercises({"Cable Oblique Crunch"}, proposed, [{"name": "Cable Oblique Crunch", "id": "existing"}], "athlete-1") == {"Cable Oblique Crunch": "existing"}
    assert len(calls) == 1
    proposed[0]["fatigue_profile"]["axial"] = float("nan")
    with pytest.raises(ValueError, match="fatigue"):
        create_missing_exercises({"Cable Oblique Crunch"}, proposed, [], "athlete-1")


def test_template_import_creates_glossary_entry_and_preserves_metadata(monkeypatch):
    from services.imports.import_parse_file import core, import_parse_ai
    from services.imports.import_apply import core as apply
    from services.imports.import_parse_file.glossary import compatible_variation

    imports = FakeImportStore()
    created = []

    class Glossary:
        async def get_glossary(self):
            return [{"id": "back", "name": "Back Extension"}]

        async def fuzzy_resolve(self, name, threshold, exercises=None):
            return "back" if name == "Back Extension" else None

    async def parse(*args):
        return {"sessions": [{"week_number": 1, "exercises": [
            {"name": "Back Extension", "glossary_id": "back", "sets": 2, "reps": 8, "rpe_target": 7},
            {"name": "Cable Twist", "sets": 2, "reps": 8},
        ]}], "new_exercises": [{
            "name": "Cable Twist", "category": "core", "fatigue_category": "accessory", "equipment": "cable",
            "primary_muscles": ["obliques"], "secondary_muscles": ["core"], "tertiary_muscles": [],
            "fatigue_profile": {"axial": 0.1, "neural": 0.2, "peripheral": 0.3, "systemic": 0.4},
            "fatigue_profile_reasoning": "Light cable rotation.",
        }]}

    async def apply_import(args):
        return {"target_sk": "template#draft"}

    def upsert(operation, args, **kwargs):
        created.append(args["exercise"])
        return {"id": args["exercise"]["id"]}

    monkeypatch.setattr(core, "_get_glossary_store", lambda pk: Glossary())
    monkeypatch.setattr(core, "_get_import_store", lambda pk: imports)
    monkeypatch.setattr(import_parse_ai, "generate_import_parse_report", parse)
    monkeypatch.setattr(apply, "import_apply", apply_import)
    monkeypatch.setattr("services.runtime.analytics_client.call", upsert)
    result = dispatch(load_operations("imports")["import_parse_file"], {
        "pk": "athlete-1", "actor_pk": "person-1", "filename": "program.csv", "import_type": "template",
        "template_import": True, "base64_content": base64.b64encode(b"day,exercise\nMonday,example\n").decode(),
    })
    parsed = imports.staged[0]["ai_parse_result"]
    draft = apply._prepare_template(parsed, [{"id": "back", "name": "Back Extension"}, created[0]])
    back, twist = draft["sessions"][0]["exercises"]
    assert result["template_sk"] == "template#draft"
    assert (back["glossary_id"], back["load_value"], back["rpe_target"]) == ("back", 7, 7)
    assert back["notes"] == ""
    assert twist["glossary_id"] == created[0]["id"]
    assert twist["notes"] == ""
    assert (created[0]["fatigue_category"], created[0]["fatigue_profile_source"]) == ("accessory", "ai_estimated")
    assert not compatible_variation("Single-leg Press", "Leg Press")
    assert compatible_variation("Single-leg Press", "One Leg Press")
