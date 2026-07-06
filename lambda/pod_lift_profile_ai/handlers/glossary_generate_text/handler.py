import json

from .core import glossary_generate_text


def handler(event, context):
    args = event.get("args", event)
    result = glossary_generate_text(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}