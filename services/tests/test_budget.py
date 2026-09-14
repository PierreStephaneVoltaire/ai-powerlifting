import importlib
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lambda/layers/pl-ai/content"))


class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = importlib.import_module("lambda.pod_budget.handlers._budget_store")
        cls.timeline = importlib.import_module("lambda.pod_budget.handlers.budget_priority_timeline.budget_timeline_ai")

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


if __name__ == "__main__":
    unittest.main()
