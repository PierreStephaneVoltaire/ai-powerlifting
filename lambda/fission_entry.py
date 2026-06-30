import json
import os
import sys
import hmac

_USERFUNC = os.environ.get("USERFUNC", "/userfunc")
if _USERFUNC not in sys.path:
    sys.path.insert(0, _USERFUNC)

import importlib

# Fission newdeploy does not merge function.spec.podspec env/envFrom into the
# runtime container, and the router drops the URL path before forwarding.
# Secrets are delivered via the Fission-native `secrets` field, which mounts
# each referenced Secret under /secrets/<namespace>/<secret-name>/<key>.
# Walk that tree and materialise every key as an environment variable so
# handler code that reads os.environ / os.getenv (AWS creds, OPENROUTER_API_KEY,
# INTERNAL_API_TOKEN, etc.) works without any podspec env.
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

# boto3 also needs the credential file path pointed at the mounted AWS secret.
for _ns in os.listdir(_SECRETS_ROOT) if os.path.isdir(_SECRETS_ROOT) else []:
    _candidate = os.path.join(_SECRETS_ROOT, _ns, "pl-aws-credentials")
    if os.path.isfile(os.path.join(_candidate, "credentials")):
        os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", os.path.join(_candidate, "credentials"))
        os.environ.setdefault("AWS_CONFIG_FILE", os.path.join(_candidate, "config"))
        os.environ.setdefault("AWS_REGION", "ca-central-1")
        os.environ.setdefault("AWS_DEFAULT_REGION", "ca-central-1")
        break

# The deploy archive ships a tool_id.txt next to the entry module so the
# correct handler can be loaded without per-function env vars (Fission
# newdeploy does not merge function.spec.podspec env into the runtime
# container, and the router drops the URL path before forwarding).
_TOOL_NAME = os.environ.get("IF_TOOL_NAME", "")
if not _TOOL_NAME:
    for _candidate in (
        os.path.join("/userfunc/deployarchive", "tool_id.txt"),
        os.path.join(_USERFUNC, "deployarchive", "tool_id.txt"),
        os.path.join(os.path.dirname(__file__), "tool_id.txt"),
    ):
        try:
            with open(_candidate) as _f:
                _TOOL_NAME = _f.read().strip()
                if _TOOL_NAME:
                    break
        except Exception:
            pass
_EXPECTED_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")


def _check_token(headers):
    if not _EXPECTED_TOKEN:
        return
    received = headers.get("X-Internal-Token", "")
    if not hmac.compare_digest(received, _EXPECTED_TOKEN):
        raise PermissionError("invalid or missing X-Internal-Token")


def main(*args):
    try:
        # Fission python-env routes /<path:path> into userfunc_call, which
        # calls this function with the path segment as a positional arg.
        # The HTTP body/headers live on the flask.request proxy global,
        # not in *args. Import it lazily so the module still loads in
        # non-flask contexts (e.g. import-time health checks).
        from flask import request as flask_request
        body = {}
        headers = {}
        path = ""
        try:
            if args:
                path = str(args[0]).strip("/")
            if not path:
                path = (flask_request.path or "").strip("/")
        except Exception:
            path = ""
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
        tool_id = _TOOL_NAME or os.environ.get("IF_TOOL_ID", "") or path.split("/")[0]
        if not tool_id:
            return {"statusCode": 500, "body": json.dumps({"error": "IF_TOOL_NAME not set"})}
        mod = importlib.import_module(tool_id + ".handler")
        event = body if body else {}
        if headers:
            event["_headers"] = headers
        result = mod.handler(event, None)
        if isinstance(result, dict) and "statusCode" in result:
            return result
        if isinstance(result, str):
            return {"statusCode": 200, "body": result}
        return {"statusCode": 200, "body": json.dumps(result, default=str)}
    except Exception as exc:
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
