import unittest
import asyncio
from unittest.mock import patch

from jsonschema import ValidationError

from services.contract import load_operations
from services.dispatch import dispatch


class FakeStore:
    pk = "athlete-1"

    async def get_library(self):
        return {
            "pk": "athlete-1",
            "sk": "federations#v1",
            "updated_at": "2026-09-13T00:00:00+00:00",
            "federations": [{"id": "ipf", "name": "IPF"}],
            "qualification_standards": [{"id": "std-1", "required_total_kg": 500}],
        }


class FederationContractTests(unittest.TestCase):
    def test_contracts_require_complete_library_replacement(self):
        operations = load_operations("federation")
        with self.assertRaises(ValidationError):
            operations["federation_user_library_set"].validate_input({"federations": []})
        operations["federation_user_library_set"].validate_input(
            {"federations": [], "qualification_standards": []}
        )

    def test_federation_list_dispatch_returns_domain_shape(self):
        module = "services.handlers.federation.federation_list.core"
        imported = __import__(module, fromlist=["_store"])
        with patch.object(imported, "_get_store", return_value=FakeStore()):
            result = dispatch(
                load_operations("federation")["federation_list"],
                {"pk": "athlete-1"},
            )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["entries"], [{"id": "ipf", "name": "IPF"}])
        self.assertEqual(result["qualification_standards"], [{"id": "std-1", "required_total_kg": 500}])

    def test_master_store_defaults_to_the_master_table(self):
        module = __import__("services.handlers.federation._federation_store", fromlist=["FederationStore"])
        names = []

        class Resource:
            def Table(self, name):
                names.append(name)
                return object()

        store = module.FederationStore.__new__(module.FederationStore)
        store._master_table_obj = None
        store._region = "ca-central-1"
        with patch.object(module, "dynamodb_resource", return_value=Resource()):
            store.master_table
        self.assertEqual(names, ["if-powerlifting-master-federations"])

    def test_master_store_scans_hash_only_catalog_and_keeps_ids(self):
        module = __import__("services.handlers.federation._federation_store", fromlist=["FederationStore"])

        class MasterTable:
            def __init__(self):
                self.calls = []

            def scan(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return {"Items": [{"pk": "FED#one", "name": "One"}], "LastEvaluatedKey": {"pk": "FED#one"}}
                return {"Items": [{"pk": "FED#two", "name": "Two"}]}

        store = module.FederationStore.__new__(module.FederationStore)
        table = MasterTable()
        store._master_table_obj = table
        result = asyncio.run(store.list_master_federations())
        self.assertEqual([item["pk"] for item in result], ["FED#one", "FED#two"])
        self.assertEqual(table.calls, [{}, {"ExclusiveStartKey": {"pk": "FED#one"}}])

    def test_master_shape_without_optional_values_validates(self):
        module = __import__("services.handlers.federation._federation_store", fromlist=["FederationStore"])
        item = module.FederationStore._normalize_federation({"pk": "FED#one", "name": "One"})
        load_operations("federation")["federation_master_list"].validate_result([item])
        self.assertEqual(item["pk"], "FED#one")


if __name__ == "__main__":
    unittest.main()
