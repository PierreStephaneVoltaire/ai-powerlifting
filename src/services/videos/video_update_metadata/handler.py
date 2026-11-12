import asyncio
import json
from decimal import Decimal

from .core import video_update_metadata


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    return str(obj)


def handler(event, context):
    result = asyncio.run(video_update_metadata(event.get("args", event)))
    return {"statusCode": 200, "body": json.dumps(result, default=_json_default)}
