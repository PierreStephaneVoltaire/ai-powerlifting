import copy
import importlib
from datetime import date
from decimal import Decimal

from services.dispatch import ROOT

merge_entries = importlib.import_module('competition_entries').merge_entries
with_competition_entries = importlib.import_module('competition_entries').with_competition_entries


def test_independent_results_replace_matching_legacy_view_without_copying_storage():
    legacy = [{'name': 'Local Meet', 'date': '2026-08-01', 'status': 'completed', 'results': {'squat_kg': 150}}, {'name': 'Older Meet', 'date': '2025-01-01', 'status': 'completed', 'results': {'squat_kg': 140}}]
    entries = [{'pk': 'athlete', 'sk': 'COMP#meet', 'name': 'Local Meet', 'start_date': '2026-08-01', 'user_status': 'completed', 'results': {'squat_kg': Decimal('180'), 'bench_kg': 100, 'deadlift_kg': 220}, 'revision': 3}, {'pk': 'athlete', 'sk': 'COMP#unused', 'name': 'Available Meet', 'start_date': '2026-08-02', 'user_status': 'available'}]
    original = copy.deepcopy((legacy, entries))
    program = with_competition_entries({'competitions': legacy}, 'athlete', entries)
    assert len(program['competitions']) == 2
    latest = program['competitions'][-1]
    assert latest['master_id'] == 'meet' and latest['revision'] == 3 and 'pk' not in latest
    assert merge_entries(program['competitions'], entries) == program['competitions']
    analytics = importlib.import_module('lambda.get_analysis_markdown.analytics')
    assert analytics._estimate_maxes_from_comps(program['competitions'], date(2026, 9, 14)) == {'squat': 180, 'bench': 100, 'deadlift': 220}
    assert (legacy, entries) == original
