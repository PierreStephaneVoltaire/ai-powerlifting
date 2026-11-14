import botocore.endpoint
import pytest


@pytest.fixture(autouse=True)
def block_live_aws(monkeypatch):
    def refuse(_endpoint, operation_model, _request_dict):
        raise RuntimeError(f"live AWS call blocked in tests: {operation_model.service_model.service_name}.{operation_model.name}")

    monkeypatch.setattr(botocore.endpoint.Endpoint, "make_request", refuse)


@pytest.fixture(autouse=True)
def memory_valkey(monkeypatch):
    from services.runtime import valkey
    records = {}
    monkeypatch.setattr(valkey, "get_json", records.get)
    monkeypatch.setattr(valkey, "set_json", records.__setitem__)
    monkeypatch.setattr(valkey, "get_text", lambda key: None if key not in records else str(records[key]))
    monkeypatch.setattr(valkey, "increment", lambda key: records.__setitem__(key, int(records.get(key, 0)) + 1))
    return records
