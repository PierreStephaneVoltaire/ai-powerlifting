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
    "fatigue_profile_estimate": "fatigue_profile_estimate",
    "glossary_estimate_e1rm": "glossary_estimate_e1rm",
    "glossary_estimate_fatigue": "glossary_estimate_fatigue",
    "glossary_estimate_muscles": "glossary_estimate_muscles",
    "glossary_generate_text": "glossary_generate_text",
    "lift_profile_estimate_stimulus": "lift_profile_estimate_stimulus",
    "lift_profile_review": "lift_profile_review",
    "lift_profile_rewrite": "lift_profile_rewrite",
    "lift_profile_rewrite_and_estimate": "lift_profile_rewrite_and_estimate",
    "muscle_group_estimate": "muscle_group_estimate",
}


def handler(event, context):
    fn_name = event.get("function") or event.get("_operation") or ""
    if not fn_name:
        return {"statusCode": 400, "body": json.dumps({"error": "missing 'function' parameter"})}
    module_name = _ROUTING.get(fn_name)
    if not module_name:
        return {"statusCode": 404, "body": json.dumps({"error": f"unknown function: {fn_name}"})}
    logger.info("[pod_lift_profile_ai] dispatching function=%s", fn_name)
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
        logger.exception("[pod_lift_profile_ai] error in function=%s", fn_name)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
