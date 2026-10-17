from services.lib.block_scope import in_block, record_block, scope_entries, scope_program


def program_with_ranges():
    return {
        "meta": {
            "current_block_id": "block-active",
            "program_start": "2026-02-15",
            "blocks": [
                {"id": "block-old", "status": "completed", "completed_at": "2026-05-31", "start_date": "2026-02-15"},
                {"id": "block-middle", "status": "completed", "completed_at": "2026-09-27", "start_date": "2026-06-01"},
                {"id": "block-active", "status": "active", "start_date": "2026-10-06"},
            ],
        }
    }


def test_dated_records_use_half_open_block_ranges_and_earliest_before_all():
    program = program_with_ranges()
    assert record_block({"date": "2026-06-01"}, "diet_notes", program) == "block-middle"
    assert record_block({"date": "2026-10-05"}, "diet_notes", program) == "block-middle"
    assert record_block({"date": "2026-10-06"}, "diet_notes", program) == "block-active"
    assert record_block({"date": "2025-01-01"}, "diet_notes", program) == "block-old"


def test_dates_win_over_stale_stamps_and_current_means_active():
    program = program_with_ranges()
    assert record_block({"date": "2025-01-01", "block_id": "archived-version"}, "diet_notes", program) == "block-old"
    assert record_block({"block": "current"}, "diet_notes", program) == "block-active"
    assert in_block({"name": "legacy"}, "block-active", "block-active") is False
    assert in_block({"block_id": "current"}, "current", "block-active") is True


def test_undated_records_have_fallback_blocks():
    program = program_with_ranges()
    assert record_block({"name": "creatine"}, "supplements", program) == "block-active"
    assert record_block({"start_week": 29}, "supplement_phases", program) == "block-middle"
    assert record_block({"start_week": 35}, "supplement_phases", program) == "block-middle"
    assert record_block({"start_week": 1, "date": "2026-10-07"}, "supplement_phases", program) == record_block({"date": "2026-10-07"}, "diet_notes", program)
    no_start = {"meta": {"current_block_id": "block-active", "blocks": program["meta"]["blocks"]}}
    assert record_block({"name": "phase"}, "supplement_phases", no_start) == "block-middle"


def test_scope_entries_keeps_unstamped_dated_records_in_their_range():
    program = program_with_ranges()
    entries = [{"date": "2026-05-31", "name": "old"}, {"date": "2026-11-07", "name": "active"}]
    assert [item["name"] for item in scope_entries(entries, "current", program, "competitions")] == ["active"]


def test_notes_nutrition_and_budget_use_record_dates_even_when_stamped_wrong():
    program = program_with_ranges()
    records = [
        {"date": "2026-09-27", "block_id": "block-active", "name": "previous"},
        {"start_date": "2026-10-06", "block_id": "block-middle", "name": "active"},
    ]
    assert [item["name"] for item in scope_entries(records, "block-middle", program, "diet_notes")] == ["previous"]
    assert [item["name"] for item in scope_entries(records, "block-active", program, "supplements")] == ["active"]
    assert [item["name"] for item in scope_entries(records, "block-active", program, "budget")] == ["active"]


def test_scope_program_filters_legacy_records_and_removes_stale_comp_date():
    program = {
        **program_with_ranges(),
        "competitions": [{"date": "2025-06-01", "name": "old"}],
        "supplements": [{"name": "creatine"}],
        "meta": {**program_with_ranges()["meta"], "comp_date": "2025-06-01", "block_notes": [{"date": "2025-06-01", "notes": "old"}]},
    }
    scoped = scope_program(program)
    assert scoped["competitions"] == []
    assert scoped["supplements"] == [{"name": "creatine"}]
    assert scoped["meta"]["block_notes"] == []
    assert "comp_date" not in scoped["meta"]


def test_session_listing_with_current_alias_keeps_stamped_active_sessions():
    from services.lib.session_store import SessionStore

    store = SessionStore.__new__(SessionStore)
    items = [
        {"date": "2026-10-06", "block_id": "block-active", "week_number": 1},
        {"date": "2026-10-12", "block_id": "current", "week_number": 2},
        {"date": "2026-08-01", "block_id": "block-previous", "week_number": 9},
    ]
    store._query_items_sync = lambda program_sk: items
    import services.lib.session_store as session_store

    original = session_store._public_session
    session_store._public_session = lambda item, phases: dict(item)
    try:
        dates = [s["date"] for s in store.list_sessions_sync("program#v1", block_id="current", active_block_id="block-active")]
    finally:
        session_store._public_session = original
    assert dates == ["2026-10-06", "2026-10-12"]
