import hmac
import os


def handler(event, context):
    expected = os.environ.get("INTERNAL_API_TOKEN", "")
    headers = event.get("headers") or {}
    provided = headers.get("x-internal-token", "") or ""
    authorized = bool(expected) and hmac.compare_digest(provided, expected)
    return {"isAuthorized": authorized, "context": {}}