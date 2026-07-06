import json
import os
import sys
import hmac
import importlib

from flask import Flask, request, jsonify

app = Flask(__name__)

_SECRETS_ROOT = "/secrets"
if os.path.isdir(_SECRETS_ROOT):
    for _ns in os.listdir(_SECRETS_ROOT):
        _ns_dir = os.path.join(_SECRETS_ROOT, _ns)
        if not os.path.isdir(_ns_dir):
            continue
        for _sec in os.listdir(_ns_dir):
            _sec_dir = os.path.join(_ns_dir, _sec)
            if not os.path.isdir(_sec_dir):
                continue
            for _key in os.listdir(_sec_dir):
                _key_path = os.path.join(_sec_dir, _key)
                if not os.path.isfile(_key_path):
                    continue
                try:
                    with open(_key_path) as _f:
                        _val = _f.read().strip()
                    if _val:
                        os.environ.setdefault(_key, _val)
                except Exception:
                    pass

for _ns in os.listdir(_SECRETS_ROOT) if os.path.isdir(_SECRETS_ROOT) else []:
    _candidate = os.path.join(_SECRETS_ROOT, _ns, "pl-aws-credentials")
    if os.path.isfile(os.path.join(_candidate, "credentials")):
        os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", os.path.join(_candidate, "credentials"))
        os.environ.setdefault("AWS_CONFIG_FILE", os.path.join(_candidate, "config"))
        os.environ.setdefault("AWS_REGION", "ca-central-1")
        os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
        break

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