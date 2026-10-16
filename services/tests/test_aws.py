from types import SimpleNamespace

from services.lib import aws


def test_dynamodb_resource_is_shared_across_requests(monkeypatch):
    created = []
    resource = SimpleNamespace()
    aws._resource_cache.clear()
    monkeypatch.setattr(aws.boto3, "resource", lambda *args, **kwargs: created.append(resource) or resource)

    first = aws.dynamodb_resource(region_name="singleton-test")
    second = aws.dynamodb_resource(region_name="singleton-test")

    assert first is second is resource
    assert created == [resource]
