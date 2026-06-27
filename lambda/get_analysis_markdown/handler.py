import json

from .core import get_analysis_markdown


def handler(event, context):
    args = event.get("args", event)
    result = get_analysis_markdown(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}