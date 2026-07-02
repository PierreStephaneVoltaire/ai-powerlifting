import json

from .core import fatigue_profile_estimate


def handler(event, context):
    args = event.get("args", event)
    result = fatigue_profile_estimate(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}