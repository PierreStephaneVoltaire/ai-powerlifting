import json
import os
import hmac
import importlib

from flask import Flask, request, jsonify

app = Flask(__name__)

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