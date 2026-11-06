import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def client() -> redis.Redis:
    return redis.Redis.from_url(os.environ.get("VALKEY_URL", "redis://pl-valkey:6379"), socket_timeout=2, socket_connect_timeout=2)


def get_json(key: str) -> Optional[Any]:
    try:
        raw = client().get(key)
    except redis.RedisError as exc:
        logger.warning("Valkey read failed for %s: %s", key, exc)
        return None
    return json.loads(raw) if raw else None


def set_json(key: str, value: Any) -> None:
    try:
        client().set(key, json.dumps(value, default=str))
    except redis.RedisError as exc:
        logger.warning("Valkey write failed for %s: %s", key, exc)
