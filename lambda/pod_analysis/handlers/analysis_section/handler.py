import json

from .core import analysis_section

_AI_SECTION_KEYS = {"ai_correlation", "program_evaluation"}


def handler(event, context):
    args = event.get("args", event)
    section = args.get("section", "")
    if section in _AI_SECTION_KEYS:
        return {"statusCode": 400, "body": "AI section not supported in lambda"}
    result = analysis_section(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}