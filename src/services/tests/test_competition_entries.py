import copy
import importlib
from datetime import date
from decimal import Decimal

normalize_entries = importlib.import_module('services.lib.competition_entries').normalize_entries
with_competition_entries = importlib.import_module('services.lib.competition_entries').with_competition_entries


def test_program_competitions_come_only_from_participation_entries():
    entries = [{'pk': 'athlete', 'sk': 'COMP#meet', 'name': 'Local Meet', 'start_date': '2026-08-01', 'user_status': 'completed', 'results': {'squat_kg': Decimal('180'), 'bench_kg': 100, 'deadlift_kg': 220}, 'revision': 3}, {'pk': 'athlete', 'sk': 'COMP#unused', 'name': 'Available Meet', 'start_date': '2026-08-02', 'user_status': 'available'}]
    original = copy.deepcopy(entries)
    program = with_competition_entries({'competitions': [{'name': 'Stale', 'date': '2025-01-01', 'status': 'completed'}]}, 'athlete', entries)
    assert [c['master_id'] for c in program['competitions']] == ['meet']
    latest = program['competitions'][-1]
    assert latest['revision'] == 3 and 'pk' not in latest and latest['date'] == '2026-08-01'
    analytics = importlib.import_module('services.lib.training_analysis')
    assert analytics._estimate_maxes_from_comps(program['competitions'], date(2026, 9, 14)) == {'squat': 180, 'bench': 100, 'deadlift': 220}
    assert entries == original


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


def test_available_directory_entries_are_not_participations():
    entries = [
        {'pk': 'athlete', 'sk': 'COMP#nationals', 'name': 'WRPF Nationals 2026', 'start_date': '2026-11-07', 'user_status': 'available'},
        {'pk': 'athlete', 'sk': 'COMP#ottawa', 'name': 'Ottawa Open', 'start_date': '2025-10-04', 'user_status': 'completed'},
        {'pk': 'athlete', 'sk': 'COMP#rumble', 'name': 'Royal City Rumble 5', 'start_date': '2027-05-01', 'user_status': 'confirmed'},
    ]
    assert [(c['date'], c['name'], c['status']) for c in normalize_entries(entries)] == [
        ('2025-10-04', 'Ottawa Open', 'completed'),
        ('2027-05-01', 'Royal City Rumble 5', 'confirmed'),
    ]
