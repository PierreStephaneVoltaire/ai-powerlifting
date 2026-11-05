import asyncio
import json

from .core import block_transition


def handler(event, context):
    return {"statusCode": 200, "body": json.dumps(asyncio.run(block_transition(event)), default=str)}
