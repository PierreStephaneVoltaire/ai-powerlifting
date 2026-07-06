import json

from .core import export_program_history


def handler(event, context):
    args = event.get("args", event)
    result = export_program_history(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}