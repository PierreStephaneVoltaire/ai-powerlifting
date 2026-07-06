import json

from .core import program_evaluation


def handler(event, context):
    args = event.get("args", event)
    result = program_evaluation(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}