import json

from .core import correlation_analysis


def handler(event, context):
    args = event.get("args", event)
    result = correlation_analysis(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}