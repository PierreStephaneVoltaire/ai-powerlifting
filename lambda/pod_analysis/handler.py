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
    "analysis_section": "analysis_section",
    "analyze_powerlifting_stats": "analyze_powerlifting_stats",
    "analyze_progression": "analyze_progression",
    "analyze_rpe_drift": "analyze_rpe_drift",
    "block_correlation_analysis": "block_correlation_analysis",
    "block_program_evaluation": "block_program_evaluation",
    "correlation_analysis": "correlation_analysis",
    "multi_block_comparison_analysis": "multi_block_comparison_analysis",
    "powerlifting_filter_categories": "powerlifting_filter_categories",
    "powerlifting_ranking_percentile": "powerlifting_ranking_percentile",
    "program_evaluation": "program_evaluation",
    "regenerate_analysis": "regenerate_analysis",
    "weekly_analysis": "weekly_analysis",
}


def handler(event, context):
    fn_name = event.get("function") or event.get("_operation") or ""
    if not fn_name:
        return {"statusCode": 400, "body": json.dumps({"error": "missing 'function' parameter"})}
    module_name = _ROUTING.get(fn_name)
    if not module_name:
        return {"statusCode": 404, "body": json.dumps({"error": f"unknown function: {fn_name}"})}
    logger.info("[pod_analysis] dispatching function=%s", fn_name)
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
        logger.exception("[pod_analysis] error in function=%s", fn_name)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
