import json

from .core import block_program_evaluation


def handler(event, context):
    args = event.get("args", event)
    result = block_program_evaluation(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}