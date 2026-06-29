import json
import os
import sys
import hmac

_USERFUNC = os.environ.get("USERFUNC", "/userfunc")
if _USERFUNC not in sys.path:
    sys.path.insert(0, _USERFUNC)

import importlib

_TOOL_NAME = os.environ.get("IF_TOOL_NAME", "")
_EXPECTED_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")


def _check_token(headers):
    if not _EXPECTED_TOKEN:
        return
    received = headers.get("X-Internal-Token", "")
    if not hmac.compare_digest(received, _EXPECTED_TOKEN):
        raise PermissionError("invalid or missing X-Internal-Token")


def main(*args):
    try:
        flask_request = args[0] if args else None
        body = {}
        headers = {}
        if flask_request is not None:
            try:
                raw = flask_request.get_data(as_text=True)
            except Exception:
                raw = ""
            if raw:
                try:
                    body = json.loads(raw)
                except Exception:
                    body = {}
            try:
                headers = dict(flask_request.headers)
            except Exception:
                headers = {}
        try:
            _check_token(headers)
        except PermissionError as auth_err:
            return {"statusCode": 401, "body": json.dumps({"error": str(auth_err)})}
        tool_id = _TOOL_NAME or os.environ.get("IF_TOOL_ID", "")
        if not tool_id:
            return {"statusCode": 500, "body": json.dumps({"error": "IF_TOOL_NAME not set"})}
        mod = importlib.import_module(tool_id + ".handler")
        event = {"args": body, "headers": headers}
        result = mod.handler(event, None)
        if isinstance(result, dict) and "statusCode" in result:
            return result
        if isinstance(result, str):
            return {"statusCode": 200, "body": result}
        return {"statusCode": 200, "body": json.dumps(result, default=str)}
    except Exception as exc:
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
