import importlib
import json
from decimal import Decimal

ROUTING = {
    "note_list_private": "note_list_private",
    "note_save_private": "note_save_private",
    "note_list_attachments": "note_list_attachments",
    "note_share": "note_share",
    "note_detach": "note_detach",
}


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    return str(value)


def handler(event, context):
    function = event.get("function") or event.get("_operation") or ""
    module_name = ROUTING.get(function)
    if not module_name:
        return {"statusCode": 404, "body": json.dumps({"code": "not_found", "message": "Unknown authored note operation"})}
    try:
        module = importlib.import_module(f"lambda.pod_authored_notes.handlers.{module_name}.handler")
        result = module.handler({key: value for key, value in event.items() if key != "function"}, context)
        if isinstance(result, dict) and "statusCode" in result:
            return result
        return {"statusCode": 200, "body": json.dumps(result, default=_json_default)}
    except Exception as exc:
        return {"statusCode": getattr(exc, "status", 500), "body": json.dumps({"code": getattr(exc, "code", "operation_failed"), "message": str(exc), **({"current_revision": exc.current_revision, "current_record": exc.current_record} if hasattr(exc, "current_revision") else {})}, default=_json_default)}
