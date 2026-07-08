import importlib
import json
import logging
import os
from decimal import Decimal
import sys

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
    "program_get": "program_get",
    "program_list": "program_list",
    "program_list_full": "program_list_full",
    "program_archive": "program_archive",
    "program_unarchive": "program_unarchive",
    "program_update_meta_field": "program_update_meta_field",
    "program_update_phases": "program_update_phases",
    "program_update_lift_profiles": "program_update_lift_profiles",
    "block_notes_get": "block_notes_get",
    "block_notes_update": "block_notes_update",
    "diet_notes_get": "diet_notes_get",
    "diet_notes_update": "diet_notes_update",
    "supplement_phases_get": "supplement_phases_get",
    "supplement_phases_update": "supplement_phases_update",
    "export_program_history": "export_program_history",
    "export_program_markdown": "export_program_markdown",
    "health_new_version": "health_new_version",
    "health_setup_initialize": "health_setup_initialize",
    "health_setup_status": "health_setup_status",
    "health_invalidate_program_cache": "health_invalidate_program_cache",
}


def handler(event, context):
    fn_name = event.get("function") or event.get("_operation") or ""
    if not fn_name:
        return {"statusCode": 400, "body": json.dumps({"error": "missing 'function' parameter"})}
    module_name = _ROUTING.get(fn_name)
    if not module_name:
        return {"statusCode": 404, "body": json.dumps({"error": f"unknown function: {fn_name}"})}
    logger.info("[pod_training_program] dispatching function=%s", fn_name)
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
        logger.exception("[pod_training_program] error in function=%s", fn_name)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}