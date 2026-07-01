import asyncio
import json

from .core import analysis_cache_mark_dirty


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(analysis_cache_mark_dirty(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
