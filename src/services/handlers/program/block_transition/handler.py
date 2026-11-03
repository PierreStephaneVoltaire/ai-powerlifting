import asyncio
import json

from .core import block_transition


def handler(event, context):
    try:
        return {"statusCode": 200, "body": json.dumps(asyncio.run(block_transition(event)), default=str)}
    except Exception as exc:
        if hasattr(exc, "current_revision"):
            return {"statusCode": 409, "body": json.dumps({"code": getattr(exc, "code", "conflict"), "expected_revision": exc.expected_revision, "current_revision": exc.current_revision, "current_record": exc.current_record}, default=str)}
        raise
