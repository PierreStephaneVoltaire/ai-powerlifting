import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import stat

from scripts.migrate_supplements import backup, cleanup_item, copy_item, migrated_item, query_programs


def av(value):
    return {"S": value}


class DynamoFake:
    def __init__(self, destination=None):
        self.destination = destination
        self.puts = []
        self.transactions = []
        self.queries = []
        self.fail_transaction = False

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {"Items": []}

    def get_item(self, **kwargs):
        return {"Item": self.destination}

    def put_item(self, **kwargs):
        self.puts.append(kwargs)
        self.destination = kwargs["Item"]

    def transact_write_items(self, **kwargs):
        self.transactions.append(kwargs)
        if self.fail_transaction:
            raise RuntimeError("TransactionCanceled: conditional check failed")
        for operation in kwargs["TransactItems"]:
            if "Put" in operation:
                self.destination = operation["Put"]["Item"]


class SupplementsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "pk": av("sir_simpalot"),
            "sk": av("program#v002"),
            "meta": {"M": {"keep": av("unrelated")}},
            "supplements": {"L": [{"M": {"name": av("creatine")}}]},
            "supplement_phases": {"L": []},
        }

    def test_query_is_consistent_and_scoped_to_program_versions(self):
        client = DynamoFake()
        query_programs(client, "if-health", "operator")
        query = client.queries[0]
        self.assertTrue(query["ConsistentRead"])
        self.assertEqual(query["ExpressionAttributeValues"][":pk"], av("operator"))
        self.assertEqual(query["ExpressionAttributeValues"][":prefix"], av("program#v"))

    def test_copy_preserves_raw_fields_and_creates_conditionally(self):
        client = DynamoFake()
        self.assertEqual(copy_item(client, self.source, "if-health", "if-supplements"), "copied")
        operations = client.transactions[0]["TransactItems"]
        self.assertEqual(operations[1]["Put"]["Item"], migrated_item(self.source))
        self.assertNotIn("meta", operations[1]["Put"]["Item"])
        self.assertIn("attribute_not_exists", operations[1]["Put"]["ConditionExpression"])

    def test_copy_refuses_conflicting_destination(self):
        client = DynamoFake(destination={"pk": av("sir_simpalot"), "sk": av("program#v002"), "supplements": av("different")})
        with self.assertRaisesRegex(RuntimeError, "destination conflict"):
            copy_item(client, self.source, "if-health", "if-supplements")
        self.assertFalse(client.puts)

    def test_copy_is_idempotent_when_destination_fields_match(self):
        client = DynamoFake(destination={**migrated_item(self.source), "extra": av("preserved")})
        self.assertEqual(copy_item(client, self.source, "if-health", "if-supplements"), "already-copied")
        self.assertFalse(client.transactions)

    def test_copy_transaction_prevents_writing_after_source_changes(self):
        client = DynamoFake()
        client.fail_transaction = True
        with self.assertRaisesRegex(RuntimeError, "source changed during copy"):
            copy_item(client, self.source, "if-health", "if-supplements")
        self.assertIsNone(client.destination)

    def test_cleanup_requires_destination_equality_and_removes_only_two_fields(self):
        client = DynamoFake(destination=migrated_item(self.source))
        self.assertEqual(cleanup_item(client, self.source, "if-health", "if-supplements"), "cleaned")
        transaction = client.transactions[0]["TransactItems"]
        update = transaction[1]["Update"]
        self.assertEqual(update["UpdateExpression"], "REMOVE #f0, #f1")
        self.assertIn("supplements", update["ExpressionAttributeNames"].values())
        self.assertIn("supplement_phases", update["ExpressionAttributeNames"].values())
        self.assertTrue(transaction[0]["ConditionCheck"]["ConditionExpression"])

    def test_cleanup_refuses_missing_or_incomplete_destination(self):
        client = DynamoFake(destination=None)
        with self.assertRaisesRegex(RuntimeError, "destination incomplete"):
            cleanup_item(client, self.source, "if-health", "if-supplements")
        self.assertFalse(client.transactions)

    def test_cleanup_keeps_source_when_transaction_condition_fails(self):
        client = DynamoFake(destination=migrated_item(self.source))
        client.fail_transaction = True
        with self.assertRaisesRegex(RuntimeError, "source retained"):
            cleanup_item(client, self.source, "if-health", "if-supplements")
        self.assertEqual(len(client.transactions), 1)

    def test_backup_is_exclusive_and_private(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "backup.json"
            backup({"sir_simpalot": [self.source]}, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                backup({}, path)


if __name__ == "__main__":
    unittest.main()
