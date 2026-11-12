import asyncio
import json

from .core import video_media_resolve


def handler(event, context):
    return {"statusCode": 200, "body": json.dumps(asyncio.run(video_media_resolve(event.get("args", event))))}
