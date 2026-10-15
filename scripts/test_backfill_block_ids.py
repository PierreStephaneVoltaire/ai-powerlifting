import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("backfill_block_ids", Path(__file__).with_name("backfill_block_ids.py"))
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)


def test_stamps_only_unscoped_records_with_the_archived_block():
    program = {
        "meta": {"current_block_id": "block-new", "blocks": [
            {"id": "block-2024", "status": "completed", "completed_at": "2025-01-01"},
            {"id": "block-2025", "status": "completed", "completed_at": "2026-10-01"},
            {"id": "block-new", "status": "active"},
        ]},
        "diet_notes": [{"date": "2026-09-01", "notes": "legacy"}, {"date": "2026-10-06", "notes": "new", "block_id": "block-new"}],
        "supplements": [{"name": "creatine", "dose": "5g"}],
        "supplement_phases": [{"phase": 1, "block": "current"}, {"phase": 1, "block": "block-2024"}],
        "competitions": [{"name": "Provincials", "date": "2026-05-01"}],
    }
    target = backfill.last_completed_block(program)
    assert target == "block-2025"
    assert backfill.plan_program(program) == {"diet_notes": 1, "supplements": 1, "supplement_phases": 1, "competitions": 1}
    backfill.stamp_program(program, target)
    assert [n.get("block_id") for n in program["diet_notes"]] == ["block-2025", "block-new"]
    assert program["supplements"][0]["block_id"] == "block-2025"
    assert [(p["block"], p.get("block_id")) for p in program["supplement_phases"]] == [("block-2025", "block-2025"), ("block-2024", None)]
    assert backfill.plan_program(program) == {"diet_notes": 0, "supplements": 0, "supplement_phases": 0, "competitions": 0}
