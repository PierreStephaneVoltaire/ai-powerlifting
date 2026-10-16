from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Any

import boto3


_resource_cache: dict[tuple[str, tuple[tuple[str, Any], ...]], Any] = {}
_resource_lock = threading.Lock()


def _region(region: str | None = None) -> str:
    return region or os.getenv("AWS_REGION", "ca-central-1")


def dynamodb_resource(service: str = "dynamodb", region_name: str | None = None, **kwargs: Any):
    if service != "dynamodb":
        raise ValueError(f"Unsupported resource service: {service}")
    region_name = _region(region_name)
    cache_key = (region_name, tuple(sorted(kwargs.items())))
    with _resource_lock:
        if cache_key not in _resource_cache:
            _resource_cache[cache_key] = boto3.resource("dynamodb", region_name=region_name, **kwargs)
        return _resource_cache[cache_key]


def table(name: str, region: str | None = None):
    return dynamodb_resource(region_name=region).Table(name)


@lru_cache(maxsize=None)
def client(service: str, region_name: str | None = None, **kwargs: Any) -> Any:
    return boto3.client(service, region_name=_region(region_name), **kwargs)
