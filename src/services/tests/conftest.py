import botocore.endpoint
import pytest


@pytest.fixture(autouse=True)
def block_live_aws(monkeypatch):
    def refuse(_endpoint, operation_model, _request_dict):
        raise RuntimeError(f"live AWS call blocked in tests: {operation_model.service_model.service_name}.{operation_model.name}")

    monkeypatch.setattr(botocore.endpoint.Endpoint, "make_request", refuse)
