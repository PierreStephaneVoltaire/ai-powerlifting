import importlib

core = importlib.import_module("services.handlers.program.export_program_history.core")

PROGRAM = {
    "meta": {
        "program_name": "Dual-Comp Peaking Program (Sunny Daze + APEX)",
        "current_block_id": "block-new",
        "blocks": [
            {"id": "sunny-daze-apex-prep", "name": "Sunny Daze + APEX Prep", "status": "completed"},
            {"id": "block-new", "label": "current", "name": "offseason session", "status": "active"},
        ],
    },
    "sessions": [],
}


def test_current_export_uses_the_active_block_name():
    assert core._export_block_name(PROGRAM, core.ACTIVE) == "offseason session"
    assert core._export_filename(PROGRAM, core.ACTIVE, {"week_start": 1, "week_end": 3}, "md") == "offseason-session_W1-W3.md"


def test_past_block_export_uses_that_block_name():
    assert core._export_block_name(PROGRAM, "sunny-daze-apex-prep") == "Sunny Daze + APEX Prep"
    assert core._export_filename(PROGRAM, "sunny-daze-apex-prep", {}, "xlsx") == "sunny-daze-apex-prep.xlsx"


def test_program_name_is_only_a_fallback():
    unnamed = {"meta": {"program_name": "Base", "current_block_id": "b", "blocks": [{"id": "b"}]}}
    assert core._export_block_name(unnamed, core.ACTIVE) == "Base"


def test_markdown_title_uses_the_block_name(tmp_path):
    export = importlib.import_module("services.handlers.program.export_program_history.export")
    program = {**PROGRAM, "meta": {**PROGRAM["meta"], "program_name": core._export_block_name(PROGRAM, core.ACTIVE)}}
    assert export._md_overview(program["meta"], "", "current", "male").splitlines()[0] == "# offseason session"
