import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

HANDLER = Path(__file__).resolve().parents[2] / "lambda" / "master-sync" / "handler.py"


def _load(monkeypatch):
    monkeypatch.setenv("COMP_MASTER_TABLE", "master")
    monkeypatch.setenv("COMP_USER_TABLE", "user")
    monkeypatch.setenv("USER_INDEX_TABLE", "index")
    fake_boto3 = ModuleType("boto3")
    fake_boto3.resource = MagicMock()
    fake_boto3.client = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    spec = importlib.util.spec_from_file_location("master_sync_handler", HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_copies_carry_the_master_id_from_the_key_even_when_the_master_item_lacks_it(monkeypatch):
    module = _load(monkeypatch)
    puts = []
    monkeypatch.setattr(module, "_collect_user_partition_keys", lambda _table: iter(["operator"]))
    monkeypatch.setattr(module, "_build_merged", lambda pk, sk, record, fields, insert: {"name": record["name"], "user_status": "available"})
    monkeypatch.setattr(module, "_put_copy", lambda table, pk, sk, merged: puts.append((pk, sk, merged)))
    module.dynamodb.Table.return_value.get_item.return_value = {}

    module._handle_master_change({"pk": "COMP#abc", "name": "Royal City Rumble 5"}, "abc")

    assert puts == [("operator", "COMP#abc", {"name": "Royal City Rumble 5", "user_status": "available", "master_id": "abc"})]
