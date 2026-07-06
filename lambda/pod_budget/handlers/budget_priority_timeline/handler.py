import json

from .core import budget_priority_timeline


def handler(event, context):
    args = event.get("args", event)
    result = budget_priority_timeline(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}