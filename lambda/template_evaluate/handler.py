import json

from .core import template_evaluate


def handler(event, context):
    args = event.get("args", event)
    result = template_evaluate(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}