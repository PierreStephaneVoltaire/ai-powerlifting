import importlib
import json
import logging
import os
import sys
from decimal import Decimal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_HANDLERS_DIR = os.path.join(os.path.dirname(__file__), "handlers")
if _HANDLERS_DIR not in sys.path:
    sys.path.insert(0, _HANDLERS_DIR)

_ROUTING = {
    "video_library_get": "video_library_get",
    "video_remove": "video_remove",
    "video_update_metadata": "video_update_metadata",
    "video_update_thumbnail": "video_update_thumbnail",
    "video_upload": "video_upload",
    "video_upload_presign": "video_upload_presign",
    "video_upload_confirm": "video_upload_confirm",
}


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    return str(obj)


def handler(event, context):
    fn_name = event.get("function") or event.get("_operation") or ""
    if not fn_name:
        return {"statusCode": 400, "body": json.dumps({"error": "missing 'function' parameter"})}
    module_name = _ROUTING.get(fn_name)
    if not module_name:
        return {"statusCode": 404, "body": json.dumps({"error": f"unknown function: {fn_name}"})}
    try:
        module = importlib.import_module(f"{module_name}.handler")
        inner_event = {key: value for key, value in event.items() if key != "function"}
        result = module.handler(inner_event, context)
        if isinstance(result, dict) and "statusCode" in result:
            return result
        return {"statusCode": 200, "body": json.dumps(result, default=_json_default)}
    except Exception as exc:
        logger.exception("[pod_videos] error in function=%s", fn_name)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
