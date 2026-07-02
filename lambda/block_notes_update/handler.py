import asyncio
import json

from .core import block_notes_update


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(block_notes_update(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}