import json

from .core import glossary_estimate_fatigue


def handler(event, context):
    args = event.get("args", event)
    result = glossary_estimate_fatigue(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}