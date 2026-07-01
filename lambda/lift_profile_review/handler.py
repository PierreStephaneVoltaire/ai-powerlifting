import json

from .core import lift_profile_review


def handler(event, context):
    args = event.get("args", event)
    result = lift_profile_review(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}