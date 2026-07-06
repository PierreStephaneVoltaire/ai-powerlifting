import json

from .core import muscle_group_estimate


def handler(event, context):
    args = event.get("args", event)
    result = muscle_group_estimate(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}