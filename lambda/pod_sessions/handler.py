import importlib
import json
import logging
import os
import sys
from decimal import Decimal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

_HANDLERS_DIR = os.path.join(os.path.dirname(__file__), "handlers")
if _HANDLERS_DIR not in sys.path:
    sys.path.insert(0, _HANDLERS_DIR)

_ROUTING = {
    "session_create": "session_create",
    "session_delete": "session_delete",
    "session_get": "session_get",
    "session_list": "session_list",
    "session_list_full": "session_list_full",
    "session_patch": "session_patch",
    "session_patch_by_date": "session_patch_by_date",
    "session_replace": "session_replace",
    "session_replace_all": "session_replace_all",
    "health_add_exercise": "health_add_exercise",
    "health_remove_exercise": "health_remove_exercise",
    "health_create_session": "health_create_session",
    "health_delete_session": "health_delete_session",
    "health_get_session": "health_get_session",
    "health_get_sessions_range": "health_get_sessions_range",
    "health_reschedule_session": "health_reschedule_session",
    "health_update_session": "health_update_session",
}


def handler(event, context):
    fn_name = event.get("function") or event.get("_operation") or ""
    if not fn_name:
        return {"statusCode": 400, "body": json.dumps({"error": "missing 'function' parameter"})}
    module_name = _ROUTING.get(fn_name)
    if not module_name:
        return {"statusCode": 404, "body": json.dumps({"error": f"unknown function: {fn_name}"})}
    logger.info("[pod_sessions] dispatching function=%s", fn_name)
    try:
        mod = importlib.import_module(f"{module_name}.handler")
        inner_event = {k: v for k, v in event.items() if k != "function"}
        result = mod.handler(inner_event, None)
        if isinstance(result, dict) and "statusCode" in result:
            return result
        if isinstance(result, str):
            return {"statusCode": 200, "body": result}
        return {"statusCode": 200, "body": json.dumps(result, default=_json_default)}
    except Exception as exc:
        logger.exception("[pod_sessions] error in function=%s", fn_name)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}