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
        from services.lib.program_store import ProgramStore
        from services.lib import storage_scope

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


def test_source_mutations_replay_deletes_invalidate_analysis_and_report_real_conflicts():
    import asyncio
    import copy
    from types import SimpleNamespace
    import pytest
    from botocore.exceptions import ClientError
    from services.dispatch import dispatch
    from services.lib.program_store import ProgramStore, ProgramRevisionConflictError

    class Table:
        def __init__(self):
            self.items = {
                "program#current": {"pk": "athlete", "sk": "program#current", "ref_sk": "program#v001", "revision": 0},
                "program#v001": {"pk": "athlete", "sk": "program#v001", "meta": {"revision": 0}, "competitions": [{"date": "2026-09-01"}]},
            }
            self.meta = SimpleNamespace(client=self)
            self.transactions = 0
            self.conflict = False

        def get_item(self, Key, **kwargs):
            item = self.items.get(Key["sk"])
            return {"Item": copy.deepcopy(item)} if item else {}

        def transact_write_items(self, TransactItems):
            self.transactions += 1
            if self.conflict:
                self.items["program#current"]["revision"] = 2
                self.items["program#v001"]["meta"]["revision"] = 2
                raise ClientError({"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems")
            for action in TransactItems:
                if "Put" in action:
                    item = action["Put"]["Item"]
                    self.items[item["sk"]] = copy.deepcopy(item)
                else:
                    self.items[action["Update"]["Key"]["sk"]]["revision"] = action["Update"]["ExpressionAttributeValues"][":next"]
            raise TimeoutError("Response lost after the committed transaction")

    store = ProgramStore("if-health", "athlete")
    store._table = table = Table()
    invalidations = []
    store._invalidate_analysis_cache = lambda: invalidations.append(store.pk)
    def remove(program):
        return {"removed": program["competitions"].pop()["date"]}
    def mutate(operation, key, revision=0):
        return asyncio.run(store.mutate_source(operation, {"date": "2026-09-01"}, revision, key, remove))
    assert mutate("delete_competition", "delete-once")["revision"] == 1
    assert mutate("delete_competition", "delete-once")["revision"] == 1
    assert table.transactions == 1
    assert invalidations == ["athlete"]
    with pytest.raises(ValueError, match="different operation"):
        mutate("complete_competition", "delete-once")
    table.items["program#v001"]["competitions"] = [{"date": "2026-09-01"}]
    table.conflict = True
    with pytest.raises(ProgramRevisionConflictError) as error:
        mutate("delete_competition", "racing-delete", 1)
    assert error.value.current_revision == 2
    assert invalidations == ["athlete"]
