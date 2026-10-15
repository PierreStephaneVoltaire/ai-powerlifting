import importlib
import unittest
from decimal import Decimal


class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = importlib.import_module("services.handlers.budget._budget_store")
        cls.timeline = importlib.import_module("services.handlers.budget.budget_priority_timeline.budget_timeline_ai")

    def test_store_helpers_preserve_dynamo_safety_and_unique_ids(self):
        converted = self.store._to_dynamo({"cost": 12.5, "nested": [1.25]})
        self.assertEqual(converted, {"cost": Decimal("12.5"), "nested": [Decimal("1.25")]})
        self.assertNotEqual(self.store._new_item_id(), self.store._new_item_id())

    def test_fallback_timeline_uses_monthly_cap(self):
        result = self.timeline._fallback_timeline({
            "config": {"monthly_cap": 150},
            "items": [{"id": "fee", "name": "Entry", "category": "competition_entry", "priority_tier": "MANDATORY", "cost": 40, "start_date": "2026-10-01"}],
        })
        self.assertEqual(result["months"][0]["budget"], 150)
        self.assertEqual(result["months"][0]["entries"][0]["suggested_month"], "2026-10")

    def test_items_and_config_are_scoped_to_the_active_block(self):
        table = MemoryBudgetTable([
            {"pk": "a", "sk": "ITEM#old", "id": "old", "name": "2025 singlet", "cost": Decimal("80"), "block_id": "block-2025"},
            {"pk": "a", "sk": "CONFIG#budget#block-2025", "config": {"monthly_cap": Decimal("300"), "currency": "CAD"}},
        ])
        store = self.store.BudgetStore("budget", "a")
        store._table = table
        store._active_block_id = lambda pk: "block-new"

        self.assertEqual(store.list_items_sync("a"), [])
        self.assertEqual([item["id"] for item in store.list_items_sync("a", block_id="block-2025")], ["old"])
        created = store.create_item_sync("a", {"name": "Meet fee", "cost": 120})
        self.assertEqual(created["block_id"], "block-new")
        self.assertEqual([item["name"] for item in store.list_items_sync("a")], ["Meet fee"])
        self.assertNotEqual(store.get_config_sync("a").get("monthly_cap"), 300)
        self.assertEqual(store.get_config_sync("a", "block-2025").get("monthly_cap"), 300)
        store.put_config_sync("a", {"monthly_cap": 200, "currency": "CAD"})
        self.assertIn(("a", "CONFIG#budget#block-new"), table.items)


class MemoryBudgetTable:
    def __init__(self, items):
        self.items = {(item["pk"], item["sk"]): dict(item) for item in items}

    def get_item(self, Key, **_kwargs):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": dict(item)} if item else {}

    def put_item(self, Item, **_kwargs):
        self.items[(Item["pk"], Item["sk"])] = dict(Item)

    def query(self, **_kwargs):
        return {"Items": [dict(item) for (_pk, sk), item in self.items.items() if sk.startswith("ITEM#")]}


if __name__ == "__main__":
    unittest.main()
