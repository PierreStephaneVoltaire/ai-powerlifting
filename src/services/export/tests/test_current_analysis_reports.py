from types import SimpleNamespace

from services.export.export_program_history import core


def test_current_export_reads_only_visible_cached_reports(monkeypatch):
    calls = []
    monkeypatch.setattr(core, '_get_glossary_sync', lambda pk: [])
    monkeypatch.setattr(core, '_get_versioned_item_sync', lambda *args: {})
    monkeypatch.setattr(core, '_build_sectioned_analysis', lambda *args, **kwargs: {'alerts': ['visible']})

    def call(operation, arguments, **kwargs):
        calls.append((operation, arguments, kwargs))
        return {'summary': operation}

    monkeypatch.setattr(core.analytics_client, 'call', call)
    store = SimpleNamespace(pk='athlete', export_access={'permissions': ['analytics:read']})
    sessions = [{'date': f'2026-01-{day:02d}', 'week_number': day, 'completed': True} for day in range(1, 5)]
    window = {'window_key': 'block', 'week_start': 1, 'week_end': 4, 'window_end': '2026-01-04'}
    bundle = core._build_analysis_bundle({}, sessions, store, window=window)

    assert bundle['weekly'] == {'alerts': ['visible']}
    assert bundle['correlation']['summary'] == 'analytics.correlation'
    assert bundle['program_evaluation']['summary'] == 'analytics.block_evaluation'
    assert all(args == {'pk': 'athlete', 'blockKey': 'current', 'cacheOnly': True, 'refresh': False} and options == {'domain': 'analytics-ai'} for _, args, options in calls)

    calls.clear()
    bundle = core._build_analysis_bundle({}, sessions, store, window={**window, 'window_key': 'previous_2', 'week_end': 2})
    assert not calls
    assert bundle['correlation'] is None and bundle['program_evaluation'] is None

    store.export_access = {'permissions': []}
    bundle = core._build_analysis_bundle({}, sessions, store, window=window)
    assert not calls
    assert bundle['weekly'] is None and bundle['correlation'] is None and bundle['program_evaluation'] is None


def test_current_export_ignores_cache_misses(monkeypatch):
    monkeypatch.setattr(core, '_get_glossary_sync', lambda pk: [])
    monkeypatch.setattr(core, '_get_versioned_item_sync', lambda *args: {})
    monkeypatch.setattr(core, '_build_sectioned_analysis', lambda *args, **kwargs: {})
    monkeypatch.setattr(core.analytics_client, 'call', lambda *args, **kwargs: {'cache_miss': True})
    store = SimpleNamespace(pk='athlete')
    bundle = core._build_analysis_bundle({}, [], store, window={'window_key': 'previous_4', 'week_start': 1, 'week_end': 4})
    assert bundle['correlation'] is None


def test_weekly_analysis_loads_stored_context_with_selected_window(monkeypatch):
    calls = []
    monkeypatch.setattr(core, '_get_glossary_sync', lambda pk: [])
    monkeypatch.setattr(core, '_get_versioned_item_sync', lambda *args: {})
    monkeypatch.setattr(core.analytics_client, 'weekly_analysis', lambda *args, **kwargs: calls.append((args, kwargs)) or {'alerts': []})
    store = SimpleNamespace(pk='athlete', export_access={'permissions': ['analytics:read']})
    window = {'window_key': 'previous_2', 'window_start': '2026-01-05', 'window_end': '2026-01-18', 'week_start': 2, 'week_end': 3}

    core._build_analysis_bundle({'sessions': [{'date': '2026-01-05'}]}, [], store, window=window)

    assert calls == [((), {
        'weeks': 2, 'block': 'current', 'window_start': '2026-01-05', 'window_end': '2026-01-18',
        'week_start': 2, 'week_end': 3, 'ref_date': '2026-01-18',
    })]

    calls.clear()
    store.export_access = {'permissions': ['program:read']}
    core._build_analysis_bundle({}, [], store, window=window)
    assert calls == []
