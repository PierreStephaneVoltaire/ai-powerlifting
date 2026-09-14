import unittest
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
        module = "lambda.pod_federation.handlers.federation_list.core"
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
        module = __import__("lambda.pod_federation.handlers._federation_store", fromlist=["FederationStore"])
        names = []

        class Resource:
            def Table(self, name):
                names.append(name)
                return object()

        store = module.FederationStore.__new__(module.FederationStore)
        store._master_table_obj = None
        store._region = "ca-central-1"
        with patch.object(module.boto3, "resource", return_value=Resource()):
            store.master_table
        self.assertEqual(names, ["if-powerlifting-master-federations"])


if __name__ == "__main__":
    unittest.main()
