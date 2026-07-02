import json

from .core import weekly_analysis


def handler(event, context):
    args = event.get("args", event)
    result = weekly_analysis(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}