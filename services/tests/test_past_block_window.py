from services.handlers.analysis_reports.analytics import _weekly_analysis_window_context


def test_past_block_window_filters_sessions_without_name_error():
    program = {
        "meta": {"program_start": "2023-07-04", "current_block": "block-2024-01-1"},
        "phases": [],
        "sessions": [],
    }
    sessions = [
        {"date": "2023-07-04", "block": "block-2023-07-2", "completed": True, "exercises": []},
        {"date": "2024-01-08", "block": "block-2024-01-1", "completed": True, "exercises": []},
    ]
    context = _weekly_analysis_window_context(program, sessions, window_start="2023-07-04", window_end="2023-12-14", ref_date="2023-12-14", weeks=24, block="block-2023-07-2")
    assert isinstance(context, dict)
