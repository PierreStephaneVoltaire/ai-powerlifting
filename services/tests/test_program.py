import unittest

from jsonschema import ValidationError

from services.contract import load_operations


class ProgramContractTests(unittest.TestCase):
    def test_program_operations_have_executable_result_schemas(self):
        operations = load_operations("program")
        self.assertIn("program_get", operations)
        self.assertTrue(all(operation.result_schema for operation in operations.values()))

    def test_program_result_shapes_cover_array_and_object_operations(self):
        operations = load_operations("program")
        self.assertEqual(operations["health_get_phases"].result_schema["type"], "array")
        self.assertEqual(operations["program_list_full"].result_schema["type"], "array")
        self.assertEqual(operations["program_get"].result_schema["type"], "object")

    def test_program_get_accepts_a_stored_program_record(self):
        load_operations("program")["program_get"].validate_result(
            {
                "meta": {"version_label": "20.0"},
                "phases": [{"name": "Peaking", "start_week": 1, "end_week": 4}],
                "current_maxes": {"squat": 185, "bench": 115, "deadlift": 220},
                "sessions": [{"date": "2026-09-13", "planned_exercises": []}],
            }
        )

    def test_program_store_resolves_current_alias_and_historical_selection(self):
        import sys
        from pathlib import Path

        layer_paths = [
            str(Path(__file__).resolve().parents[2] / "lambda/layers/pl-program/python"),
            str(Path(__file__).resolve().parents[2] / "lambda/layers/pl-core/python"),
        ]
        original_path = sys.path[:]
        sys.path[:0] = [path for path in layer_paths if path not in sys.path]
        try:
            from program_store import ProgramStore
            import storage_scope
        finally:
            sys.path[:] = original_path

        class Table:
            def __init__(self):
                self.items = {
                    ("athlete", "program#current"): {"pk": "athlete", "sk": "program#current", "ref_sk": "program#v002", "version": 2},
                    ("athlete", "program#v001"): {"pk": "athlete", "sk": "program#v001", "meta": {"version_label": "1.0"}},
                    ("athlete", "program#v002"): {"pk": "athlete", "sk": "program#v002", "meta": {"version_label": "2.0"}},
                }

            def get_item(self, Key):
                item = self.items.get((Key["pk"], Key["sk"]))
                return {"Item": item} if item else {}

        def load(selector):
            store = ProgramStore("unused", "athlete")
            store._selected_program_sk = selector
            store._table = Table()
            store._get_session_store = lambda: type("Sessions", (), {"list_sessions_sync": lambda *_: []})()
            return store

        omitted = load(None)
        current = load("program#current")
        historical = load("program#v001")
        assert omitted._current_program_sk_sync() == "program#v002"
        assert current._current_program_sk_sync() == "program#v002"
        assert historical._current_program_sk_sync() == "program#v001"
        assert omitted._load_program_sync()["meta"]["version_label"] == "2.0"
        assert current._load_program_sync()["meta"]["version_label"] == "2.0"
        assert historical._load_program_sync()["meta"]["version_label"] == "1.0"

    def test_mutations_reject_missing_payloads(self):
        operations = load_operations("program")
        operations.update(load_operations("lift-profiles"))
        for name in ("program_update_meta_field", "program_update_phases", "program_update_lift_profiles"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    operations[name].validate_input({})

    def test_legacy_results_validate(self):
        operations = load_operations("program")
        operations["health_get_diet_notes"].validate_result([])
        operations["health_delete_diet_note"].validate_result({"deleted": "2026-09-13"})
        operations["program_archive"].validate_result({"success": True})


if __name__ == "__main__":
    unittest.main()
