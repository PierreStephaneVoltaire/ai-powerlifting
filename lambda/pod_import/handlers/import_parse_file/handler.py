import json

from .core import import_parse_file


def handler(event, context):
    args = event.get("args", event)
    result = import_parse_file(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
