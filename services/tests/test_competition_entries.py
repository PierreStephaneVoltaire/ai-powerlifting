import copy
import importlib
from datetime import date
from decimal import Decimal

merge_entries = importlib.import_module('services.lib.competition_entries').merge_entries
with_competition_entries = importlib.import_module('services.lib.competition_entries').with_competition_entries


def test_independent_results_replace_matching_legacy_view_without_copying_storage():
    legacy = [{'name': 'Local Meet', 'date': '2026-08-01', 'status': 'completed', 'results': {'squat_kg': 150}}, {'name': 'Older Meet', 'date': '2025-01-01', 'status': 'completed', 'results': {'squat_kg': 140}}]
    entries = [{'pk': 'athlete', 'sk': 'COMP#meet', 'name': 'Local Meet', 'start_date': '2026-08-01', 'user_status': 'completed', 'results': {'squat_kg': Decimal('180'), 'bench_kg': 100, 'deadlift_kg': 220}, 'revision': 3}, {'pk': 'athlete', 'sk': 'COMP#unused', 'name': 'Available Meet', 'start_date': '2026-08-02', 'user_status': 'available'}]
    original = copy.deepcopy((legacy, entries))
    program = with_competition_entries({'competitions': legacy}, 'athlete', entries)
    assert len(program['competitions']) == 2
    latest = program['competitions'][-1]
    assert latest['master_id'] == 'meet' and latest['revision'] == 3 and 'pk' not in latest
    assert merge_entries(program['competitions'], entries) == program['competitions']
    analytics = importlib.import_module('services.handlers.analysis_reports.analytics')
    assert analytics._estimate_maxes_from_comps(program['competitions'], date(2026, 9, 14)) == {'squat': 180, 'bench': 100, 'deadlift': 220}
    assert (legacy, entries) == original


def test_load_entries_reads_only_participations_through_the_date_index():
    from services.lib import competition_entries

    class Table:
        def __init__(self):
            self.calls = []

        def query(self, **arguments):
            self.calls.append(arguments)
            return {"Items": [{"pk": "a", "sk": "COMP#nats", "user_status": "confirmed", "entry_date": "2026-11-01"}]}

    table = Table()
    entries = competition_entries.load_entries("a", "2026-10-01", None, table=table)
    assert [entry["sk"] for entry in entries] == ["COMP#nats"]
    assert table.calls[0]["IndexName"] == "entries-by-date"
    assert "ConsistentRead" not in table.calls[0]


def test_load_entries_falls_back_to_partition_query_until_index_exists():
    from services.lib import competition_entries
    from botocore.exceptions import ClientError

    class Table:
        def query(self, **arguments):
            if arguments.get("IndexName"):
                raise ClientError({"Error": {"Code": "ValidationException", "Message": "no index"}}, "Query")
            return {"Items": [
                {"pk": "a", "sk": "COMP#dir", "user_status": "available", "start_date": "2026-12-01"},
                {"pk": "a", "sk": "COMP#old", "user_status": "completed", "start_date": "2025-03-01"},
                {"pk": "a", "sk": "COMP#nats", "user_status": "confirmed", "start_date": "2026-11-01"},
            ]}

    entries = competition_entries.load_entries("a", "2026-01-01", None, table=Table())
    assert [entry["sk"] for entry in entries] == ["COMP#nats"]
