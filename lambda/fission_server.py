import json
import os
import sys
import hmac
import importlib

from flask import Flask, request, jsonify

app = Flask(__name__)

_AWS_CREDS_DIR = "/secrets/aws-credentials"
if os.path.isdir(_AWS_CREDS_DIR):
    for _key in os.listdir(_AWS_CREDS_DIR):
        _key_path = os.path.join(_AWS_CREDS_DIR, _key)
        if not os.path.isfile(_key_path):
            continue
        try:
            with open(_key_path) as _f:
                _val = _f.read().strip()
            if _val:
                os.environ.setdefault(_key, _val)
        except Exception:
            pass

_creds_file = os.path.join(_AWS_CREDS_DIR, "credentials")
if os.path.isfile(_creds_file):
    os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", _creds_file)
    os.environ.setdefault("AWS_CONFIG_FILE", os.path.join(_AWS_CREDS_DIR, "config"))
    os.environ.setdefault("AWS_REGION", "ca-central-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")

_PL_SECRETS_DIR = "/secrets/pl-secrets"
if os.path.isdir(_PL_SECRETS_DIR):
    for _key in os.listdir(_PL_SECRETS_DIR):
        _key_path = os.path.join(_PL_SECRETS_DIR, _key)
        if not os.path.isfile(_key_path):
            continue
        try:
            with open(_key_path) as _f:
                _val = _f.read().strip()
            if _val:
                os.environ.setdefault(_key, _val)
        except Exception:
            pass

_TOOL_NAME = ""
_tool_id_path = os.path.join(os.path.dirname(__file__), "tool_id.txt")
if os.path.isfile(_tool_id_path):
    with open(_tool_id_path) as _f:
        _TOOL_NAME = _f.read().strip()
if not _TOOL_NAME:
    _TOOL_NAME = os.environ.get("IF_TOOL_NAME", "")

_EXPECTED_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")


def _check_token(headers):
    if not _EXPECTED_TOKEN:
        return
    received = headers.get("X-Internal-Token", "")
    if not hmac.compare_digest(received, _EXPECTED_TOKEN):
        raise PermissionError("invalid or missing X-Internal-Token")


@app.route("/<path:path>", methods=["POST", "GET"])
@app.route("/", methods=["POST", "GET"])
def handle(path=""):
    try:
        _check_token(request.headers)
        tool_id = _TOOL_NAME or os.environ.get("IF_TOOL_ID", "") or path.strip("/").split("/")[0]
        if not tool_id:
            return jsonify({"error": "IF_TOOL_NAME not set"}), 500
        mod = importlib.import_module(tool_id + ".handler")
        raw = request.get_data(as_text=True)
        body = json.loads(raw) if raw else {}
        result = mod.handler(body, None)
        if isinstance(result, dict) and "statusCode" in result:
            return jsonify(result), result["statusCode"]
        if isinstance(result, str):
            return result, 200
        return json.dumps(result, default=str), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888)