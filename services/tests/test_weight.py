import importlib


from services.contract import load_operations
from services.dispatch import dispatch


class FakeWeightStore:
    def __init__(self):
        self.logs = {}

    async def get_log(self, pk, version, block_id=None):
        return self.logs.get((pk, version), {"pk": pk, "sk": f"weight_log#{version}", "version": version, "entries": [], "updated_at": "now"})

    async def add_entry(self, pk, version, entry):
        log = await self.get_log(pk, version)
        entries = [item for item in log["entries"] if item["date"] != entry["date"]]
        log = {**log, "entries": sorted([*entries, entry], key=lambda item: item["date"], reverse=True)}
        self.logs[(pk, version)] = log
        return log

    async def remove_entry(self, pk, version, date):
        log = await self.get_log(pk, version)
        log = {**log, "entries": [item for item in log["entries"] if item["date"] != date]}
        self.logs[(pk, version)] = log
        return log


def test_weight_operations_round_trip_and_aliases(monkeypatch):
    store = FakeWeightStore()
    for name in ("weight_log_add", "weight_add_entry", "weight_log_get", "weight_get_log", "weight_log_remove", "weight_remove_entry"):
        module_name = {
            "weight_log_add": "lambda.pod_weight.handlers.weight_log_add.core",
            "weight_add_entry": "lambda.pod_weight.handlers.weight_add_entry.core",
            "weight_log_get": "lambda.pod_weight.handlers.weight_log_get.core",
            "weight_get_log": "lambda.pod_weight.handlers.weight_get_log.core",
            "weight_log_remove": "lambda.pod_weight.handlers.weight_log_remove.core",
            "weight_remove_entry": "lambda.pod_weight.handlers.weight_remove_entry.core",
        }[name]
        monkeypatch.setattr(importlib.import_module(module_name), "get_store", lambda: store)

    operations = load_operations("weight-log")
    result = dispatch(operations["weight_log_add"], {"pk": "athlete-1", "version": "v001", "date": "2026-09-13", "weight_kg": 76.25})
    assert result["entries"] == [{"date": "2026-09-13", "kg": 76.25}]
    assert dispatch(operations["weight_get_log"], {"pk": "athlete-1", "version": "v001"})["entries"] == result["entries"]

    dispatch(operations["weight_add_entry"], {"pk": "athlete-1", "version": "v001", "entry": {"date": "2026-09-13", "kg": 77.0, "body_fat_pct": 15.2}})
    assert dispatch(operations["weight_log_get"], {"pk": "athlete-1", "version": "v001"})["entries"][0]["kg"] == 77
    assert dispatch(operations["weight_log_remove"], {"pk": "athlete-1", "version": "v001", "date": "2026-09-13"})["entries"] == []
    assert dispatch(operations["weight_remove_entry"], {"pk": "athlete-1", "version": "v001", "date": "2026-09-13"})["entries"] == []


def test_weight_mutations_require_their_fields():
    operations = load_operations("weight-log")
    for name in ("weight_log_add", "weight_add_entry", "weight_log_remove", "weight_remove_entry"):
        with __import__("pytest").raises(Exception):
            operations[name].validate_input({})



class MemoryTable:
    def __init__(self, items):
        self.items = {(item["pk"], item["sk"]): dict(item) for item in items}

    def get_item(self, Key, **_kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": dict(item)} if item else {}

    def put_item(self, Item, **_kwargs):
        self.items[(Item["pk"], Item["sk"])] = dict(Item)


def test_weight_log_is_scoped_to_the_active_block(monkeypatch):
    import asyncio
    store_module = importlib.import_module("lambda.pod_weight.handlers._weight_store")
    monkeypatch.setattr(store_module, "invalidate_analysis_caches", lambda *_a, **_k: None)
    table = MemoryTable([
        {"pk": "a", "sk": "program#current", "ref_sk": "program#v002", "current_block_id": "block-new"},
        {"pk": "a", "sk": "weight_log#current", "version": "current", "updated_at": "t0", "entries": [
            {"date": "2025-01-06", "kg": 90, "block_id": "block-2025"},
            {"date": "2026-10-06", "kg": 92, "block_id": "block-new"},
        ]},
    ])
    store = store_module.WeightStore.__new__(store_module.WeightStore)
    store.table, store.region = table, "ca-central-1"

    assert [e["date"] for e in asyncio.run(store.get_log("a", "current"))["entries"]] == ["2026-10-06"]
    assert [e["date"] for e in asyncio.run(store.get_log("a", "current", "block-2025"))["entries"]] == ["2025-01-06"]

    added = asyncio.run(store.add_entry("a", "current", {"date": "2025-01-06", "kg": 93}))
    assert sorted(e["date"] for e in added["entries"]) == ["2025-01-06", "2026-10-06"]
    stored = table.items[("a", "weight_log#current")]["entries"]
    assert {(e["date"], e["block_id"]) for e in stored} == {("2025-01-06", "block-2025"), ("2025-01-06", "block-new"), ("2026-10-06", "block-new")}
