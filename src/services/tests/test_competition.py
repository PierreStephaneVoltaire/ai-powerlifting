import importlib
import copy

import pytest

from services.contract import load_operations
from services.dispatch import dispatch


class FakeProgramStore:
    pk = "operator"

    def __init__(self):
        self.program = {}

    async def get_program(self):
        return self.program


def test_attempt_calculation_is_validated_and_structured(monkeypatch):
    module = importlib.import_module("services.handlers.competition.calculate_attempts.core")
    store = FakeProgramStore()
    store.program = {"operator_prefs": {"attempt_jumps": {"squat": {"j1": 20, "j2": 20}}}, "current_maxes": {"squat": 180}}
    monkeypatch.setattr(module, "_get_store", lambda: store)
    operation = load_operations("competition")["calculate_attempts"]
    result = dispatch(operation, {"pk": "athlete-1", "lift": "squat", "opener_kg": 160})
    assert result["attempt_1_kg"] == 160
    assert result["attempt_2_kg"] == 180
    assert result["warnings"] == ["Attempt 3 (200.0kg) exceeds current max of 180kg — confirm this is a target PR."]
    with pytest.raises(Exception):
        dispatch(operation, {"pk": "athlete-1", "lift": "snatch", "opener_kg": 100})


def test_user_competitions_use_a_partition_query(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [{"pk": "athlete-1", "sk": "COMP#meet", "name": "Meet"}]}

        def scan(self, **_kwargs):
            raise AssertionError("user competition list must not scan the table")

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")
    assert module.list_competitions({"pk": "athlete-1"}) == [{"name": "Meet", "master_id": "meet", "units": "kg"}]


def test_user_competitions_show_every_participation_unless_a_block_is_requested(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [
                {"pk": "a", "sk": "COMP#dir", "name": "Directory meet", "user_status": "available", "start_date": "2026-12-01"},
                {"pk": "a", "sk": "COMP#old", "name": "2025 Provincials", "user_status": "completed", "block_id": "block-2025", "start_date": "2025-03-01"},
                {"pk": "a", "sk": "COMP#new", "name": "2026 Nationals", "user_status": "confirmed", "block_id": "block-new", "start_date": "2026-11-01"},
            ]}

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")
    assert [c["name"] for c in module.list_competitions({"pk": "a"})] == ["2025 Provincials", "2026 Nationals", "Directory meet"]
    assert [c["name"] for c in module.list_competitions({"pk": "a", "block_id": "block-2025"})] == ["2025 Provincials", "Directory meet"]
    assert [c["name"] for c in module.list_competitions({"pk": "a", "block_id": "block-new"})] == ["2026 Nationals", "Directory meet"]


def test_user_competitions_match_country_names_against_iso_venue_codes(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [
                {"pk": "a", "sk": "COMP#on", "name": "Ontario meet", "venue_country": "CA", "venue_state": "ON", "start_date": "2026-12-01"},
                {"pk": "a", "sk": "COMP#qc", "name": "Quebec meet", "venue_country": "CA", "venue_state": "QC", "start_date": "2026-12-02"},
                {"pk": "a", "sk": "COMP#tx", "name": "Texas meet", "venue_country": "US", "venue_state": "TX", "start_date": "2026-12-03"},
            ]}

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: None)
    names = lambda args: [c["name"] for c in module.list_competitions({"pk": "a", **args})]
    assert names({"country": "CANADA"}) == ["Ontario meet", "Quebec meet"]
    assert names({"country": "ca", "state": "on"}) == ["Ontario meet"]
    assert names({"country": "USA"}) == ["Texas meet"]


def test_user_competitions_keep_a_stored_master_id_and_fill_a_missing_one_from_the_key(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [
                {"pk": "a", "sk": "COMP#from-key", "name": "Royal City Rumble 5", "start_date": "2027-05-01"},
                {"pk": "a", "sk": "COMP#key", "master_id": "stored", "name": "WRPF Nationals", "start_date": "2026-11-07"},
            ]}

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: None)
    assert [(c["name"], c["master_id"]) for c in module.list_competitions({"pk": "a"})] == [
        ("WRPF Nationals", "stored"),
        ("Royal City Rumble 5", "from-key"),
    ]


def test_participations_without_a_block_are_listed_so_they_can_be_edited(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")

    class Table:
        def query(self, **_kwargs):
            return {"Items": [
                {"pk": "a", "sk": "COMP#coldfront", "name": "Coldfront 2", "user_status": "confirmed", "start_date": "2026-11-14"},
                {"pk": "a", "sk": "COMP#rumble", "name": "Royal City Rumble 5", "user_status": "confirmed", "block_id": "block-new", "start_date": "2027-05-01"},
            ]}

    monkeypatch.setattr(module, "_get_table", lambda: Table())
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")
    assert [c["name"] for c in module.list_competitions({"pk": "a"})] == ["Coldfront 2", "Royal City Rumble 5"]


class FakeCompetitionTable:
    name = "competitions"

    def __init__(self):
        self.items = {("athlete-1", "COMP#meet"): {"pk": "athlete-1", "sk": "COMP#meet", "master_id": "meet", "notes": ""}}
        self.updates = 0

    def get_item(self, Key, ConsistentRead=False):
        item = self.items.get(tuple(Key.values()))
        return {"Item": copy.deepcopy(item)} if item is not None else {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues, **kwargs):
        assert "ConditionExpression" not in kwargs
        item = self.items[tuple(Key.values())]
        sets, _, removes = UpdateExpression.removeprefix("SET ").partition(" REMOVE ")
        for assignment in sets.split(", "):
            name, value = (part.strip() for part in assignment.split("="))
            item[ExpressionAttributeNames[name]] = copy.deepcopy(ExpressionAttributeValues[value])
        for name in filter(None, (part.strip() for part in removes.split(","))):
            item.pop(ExpressionAttributeNames[name], None)
        self.updates += 1


def test_competition_update_is_a_plain_last_write_wins_save(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")
    table = FakeCompetitionTable()
    monkeypatch.setattr(module, "_get_table", lambda: table)
    first = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"notes": "first"}})
    second = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"notes": "second"}})
    assert (first["notes"], second["notes"]) == ("first", "second")
    assert "revision" not in second
    assert table.items[("athlete-1", "COMP#meet")]["notes"] == "second"
    assert table.updates == 2
    assert not any(sk != "COMP#meet" for _, sk in table.items)


def test_competition_report_resave_keeps_attempt_ids(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")
    table = FakeCompetitionTable()
    monkeypatch.setattr(module, "_get_table", lambda: table)
    report = {"attempts": [{"lift": "squat", "attempt_number": 1, "kg": 100, "result": "made"}]}
    result = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"post_meet_report": report}})
    attempt_id = result["post_meet_report"]["attempts"][0]["attempt_id"]
    resaved = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"post_meet_report": report}})
    assert resaved["post_meet_report"]["attempts"][0]["attempt_id"] == attempt_id


def test_entering_a_meet_indexes_it_by_date_and_block_and_withdrawing_unindexes_it(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_list_competitions.core")
    table = FakeCompetitionTable()
    table.items[("athlete-1", "COMP#meet")]["start_date"] = "2026-11-01"
    monkeypatch.setattr(module, "_get_table", lambda: table)
    monkeypatch.setattr(module, "active_block_id_for", lambda pk: "block-new")

    entered = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"user_status": "confirmed"}})
    stored = table.items[("athlete-1", "COMP#meet")]
    assert (entered["entry_date"], entered["block_id"]) == ("2026-11-01", "block-new")
    assert (stored["entry_date"], stored["block_id"]) == ("2026-11-01", "block-new")

    withdrawn = module.update_user_competition({"pk": "athlete-1", "master_id": "meet", "patch": {"user_status": "available"}})
    assert "entry_date" not in withdrawn
    assert "entry_date" not in table.items[("athlete-1", "COMP#meet")]


def test_projection_snapshot_targets_entries_one_week_out(monkeypatch):
    module = importlib.import_module("services.handlers.competition.health_snapshot_competition_projection.core")
    analytics = importlib.import_module("services.handlers.competition.health_snapshot_competition_projection.analytics")
    monkeypatch.setattr(analytics, "meet_projection", lambda *_args, **_kwargs: {"squat": 200, "bench": 125, "deadlift": 240, "total": 565})
    from datetime import date
    entries = [
        {"sk": "COMP#rumble", "name": "Royal City Rumble 5", "start_date": "2027-05-01", "user_status": "confirmed"},
        {"sk": "COMP#done", "name": "Already", "start_date": "2027-05-01", "user_status": "confirmed", "projected_at_t_minus_1w": {"total_kg": 1}},
        {"sk": "COMP#dir", "name": "Directory", "start_date": "2027-05-01", "user_status": "available"},
        {"sk": "COMP#later", "name": "Later", "start_date": "2027-06-01", "user_status": "confirmed"},
    ]
    updates = module.snapshot_entries({"sessions": []}, entries, date(2027, 4, 24))
    assert [(u["sk"], u["projected_at_t_minus_1w"]["total_kg"], u["projection_snapshot_date"]) for u in updates] == [("COMP#rumble", 565, "2027-04-24")]
