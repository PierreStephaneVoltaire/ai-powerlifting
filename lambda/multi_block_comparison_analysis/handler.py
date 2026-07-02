import json

from .core import multi_block_comparison_analysis


def handler(event, context):
    args = event.get("args", event)
    result = multi_block_comparison_analysis(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}